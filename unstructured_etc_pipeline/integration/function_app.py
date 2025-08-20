import logging
import azure.functions as func
from utils.dbsearch import check_last_version,update_last_version,check_delete_version,rollback_seed_version_to_local
from utils.aisearchsync import check_local_integration_sync_status
import utils.constants as VARIABLE
from utils.cosmosmigration import transfer_data
from utils.cosmossearch import local_search_cont_sync_check,cosmos_check
from utils.aisearchmigration import migration
from utils.cosmosdelete import delete_old_versions_cosmos, delete_old_versions_cosmos_seed
from utils.aisearchdelete import delete_old_versions_aisearch
from utils.verification_runner import run_verification_for_qaset
from utils.dbsearch import history_insert
from datetime import datetime
import asyncio
import logging
import os
import traceback
from dotenv import load_dotenv
# load_dotenv(override=True)
logging.basicConfig(level=logging.ERROR)
logging.getLogger("azure").setLevel(logging.WARNING)
logging.getLogger("azure.core.pipeline.policies.http_logging_policy").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
app = func.FunctionApp()
batch_lock = asyncio.Lock()
INTEGRATION_INDEX_NAME = os.getenv("INTEGRATION_INDEX_NAME")
SYSTEM_LOCATION = os.getenv("SYSTEM_LOCATION")

@app.function_name(name=f"migration_function_trigger_{SYSTEM_LOCATION}")
@app.schedule(schedule="0 */60 * * * *", arg_name="myTimer", run_on_startup=False,
              use_monitor=False) 
async def timer_trigger(myTimer: func.TimerRequest) -> None:
    if myTimer.past_due:
        logging.info(f'migration_function_trigger_{SYSTEM_LOCATION}: The timer is past due!')
        
    try:
        CURRENT_TIME = datetime.now()
        CURRENT_VERSION = CURRENT_TIME.strftime('%y%m%d%H')
        SYSTEM_NAME = 'integration'
        history_insert(system_name=SYSTEM_NAME, work_type='BATCH', version=CURRENT_VERSION, count=1)
        
        async with batch_lock:
            logging.info(f"migration_function_trigger_{SYSTEM_LOCATION} : Batch Start!")
            system_version_info =  check_last_version()
            logging.info(system_version_info)
            #시스템 별 수행
            for info in system_version_info:
                attempt_count = 0
                while attempt_count < 3:
                    INDEX_NAME,SEED_CONT_VER,LOCAL_INDEX_VER,SEED_CONT_NAME = info[0],info[1],info[2],info[5]
                    logging.info(f"{INDEX_NAME} loop start!")
                    logging.info(f"{INDEX_NAME} cosmos check")
                    if 'media' in INDEX_NAME:
                        if SEED_CONT_VER != LOCAL_INDEX_VER:
                            logging.info(f"{INDEX_NAME} SEED_CONT_VER != LOCAL_INDEX_VER")
                            if cosmos_check(INDEX_NAME,SEED_CONT_VER,SEED_CONT_NAME):
                                verification_result = run_verification_for_qaset(INDEX_NAME, SEED_CONT_VER)
                                if verification_result == 1:
                                    update_last_version(VARIABLE.LOCAL,INDEX_NAME,SEED_CONT_VER)
                                else:
                                    rollback_seed_version_to_local(INDEX_NAME, LOCAL_INDEX_VER)
                                    history_insert("PIPELINE_ROLLBACK",INDEX_NAME, SEED_CONT_VER, 0)
                                    break

                        local_system_version_info = check_last_version(INDEX_NAME)[0]
                        logging.info(local_system_version_info)
                        INDEX_NAME,SEED_CONT_VER,LOCAL_INDEX_VER,INTEGRATION_INDEX_VER,SEARCH_CONT_VER = local_system_version_info[0],local_system_version_info[1],local_system_version_info[2],local_system_version_info[3],local_system_version_info[4]
                        logging.info(f"{INDEX_NAME} search_cont check")
                        if LOCAL_INDEX_VER != SEARCH_CONT_VER:
                            task = asyncio.create_task(transfer_data(INDEX_NAME,LOCAL_INDEX_VER))
                            await task
                            sync_status = local_search_cont_sync_check(INDEX_NAME,LOCAL_INDEX_VER)
                            if sync_status:update_last_version(VARIABLE.SEARCH_CONT,INDEX_NAME,LOCAL_INDEX_VER)
                            
                        for_checkallsystemsync_version_info =  check_last_version(INDEX_NAME)[0]
                        INDEX_NAME,SEED_CONT_VER,LOCAL_INDEX_VER,INTEGRATION_INDEX_VER,SEARCH_CONT_VER = for_checkallsystemsync_version_info[0],for_checkallsystemsync_version_info[1],for_checkallsystemsync_version_info[2],for_checkallsystemsync_version_info[3],for_checkallsystemsync_version_info[4]
                        if SEED_CONT_VER == SEARCH_CONT_VER:
                            logging.info(f"{INDEX_NAME} SEED_CONT_VER == SEARCH_CONT_VER, Can exit loop")
                            break
                    else:
                        if SEED_CONT_VER != LOCAL_INDEX_VER:
                            logging.info(f"{INDEX_NAME} SEED_CONT_VER != LOCAL_INDEX_VER")
                            if cosmos_check(INDEX_NAME,SEED_CONT_VER,SEED_CONT_NAME):
                                verification_result = run_verification_for_qaset(INDEX_NAME, SEED_CONT_VER)
                                if verification_result == 1:
                                    update_last_version(VARIABLE.LOCAL,INDEX_NAME,SEED_CONT_VER)
                                else:
                                    rollback_seed_version_to_local(INDEX_NAME, LOCAL_INDEX_VER)
                                    history_insert("PIPELINE_ROLLBACK",INDEX_NAME, SEED_CONT_VER, 0)
                                    break
                        local_system_version_info = check_last_version(INDEX_NAME)[0]
                        logging.info(local_system_version_info)
                        INDEX_NAME,LOCAL_INDEX_VER,INTEGRATION_INDEX_VER = local_system_version_info[0],local_system_version_info[2],local_system_version_info[3]
                        logging.info(f"{INDEX_NAME} integration check")
                        if LOCAL_INDEX_VER != INTEGRATION_INDEX_VER:
                            task = asyncio.create_task(migration(INDEX_NAME, INTEGRATION_INDEX_NAME, 100, LOCAL_INDEX_VER))
                            await task
                            
                            sync_status = check_local_integration_sync_status(INDEX_NAME, LOCAL_INDEX_VER)
                            if sync_status:
                                logging.info("Integration sync status: Successful")
                            else:
                                logging.info("Integration sync status: Failed")
                            if sync_status:
                                update_last_version(VARIABLE.INTEGRATION,INDEX_NAME,LOCAL_INDEX_VER)
                            
                        integration_system_version_info =  check_last_version(INDEX_NAME)[0]
                        INDEX_NAME,SEED_CONT_VER,LOCAL_INDEX_VER,INTEGRATION_INDEX_VER,SEARCH_CONT_VER = integration_system_version_info[0],integration_system_version_info[1],integration_system_version_info[2],integration_system_version_info[3],integration_system_version_info[4]
                        logging.info(f"{INDEX_NAME} search_cont check")
                        if INTEGRATION_INDEX_VER != SEARCH_CONT_VER:
                            task = asyncio.create_task(transfer_data(INDEX_NAME,LOCAL_INDEX_VER))
                            await task
                            sync_status = local_search_cont_sync_check(INDEX_NAME,LOCAL_INDEX_VER)
                            if sync_status:update_last_version(VARIABLE.SEARCH_CONT,INDEX_NAME,LOCAL_INDEX_VER)
                        for_checkallsystemsync_version_info =  check_last_version(INDEX_NAME)[0]
                        INDEX_NAME,SEED_CONT_VER,LOCAL_INDEX_VER,INTEGRATION_INDEX_VER,SEARCH_CONT_VER = for_checkallsystemsync_version_info[0],for_checkallsystemsync_version_info[1],for_checkallsystemsync_version_info[2],for_checkallsystemsync_version_info[3],for_checkallsystemsync_version_info[4]
                        if SEED_CONT_VER == SEARCH_CONT_VER:
                            logging.info(f"{INDEX_NAME} SEED_CONT_VER == SEARCH_CONT_VER, Can exit loop")
                            break
                    attempt_count += 1
                    logging.info(f"{INDEX_NAME} loop end!")
                
            logging.info(f"migration_function_trigger_{SYSTEM_LOCATION}: Batch End!")
    
    except Exception as e:
        trace = traceback.format_exception(type(e), e, e.__traceback__)
        error_message = "".join(trace)
        history_insert(system_name=SYSTEM_NAME, work_type='ERROR', version=CURRENT_VERSION, count=1, error=error_message) # Error History 
    finally:
        history_insert(system_name=SYSTEM_NAME, work_type='BATCH_END', version=CURRENT_VERSION, count=1)

@app.function_name(name=f"http_migration_function_trigger_{SYSTEM_LOCATION}")
@app.route(route=f"http_migration_function_trigger_{SYSTEM_LOCATION}", auth_level=func.AuthLevel.ANONYMOUS)
async def HttpTrigger(req: func.HttpRequest) -> func.HttpResponse:    
    logging.info(f'migration_function_trigger_{SYSTEM_LOCATION}: Python HTTP trigger function processed a request.')
        
    try:
        CURRENT_TIME = datetime.now()
        CURRENT_VERSION = CURRENT_TIME.strftime('%y%m%d%H')
        SYSTEM_NAME = 'integration'
        history_insert(system_name=SYSTEM_NAME, work_type='BATCH', version=CURRENT_VERSION, count=1)
        
        async with batch_lock:
            logging.info(f"migration_function_trigger_{SYSTEM_LOCATION} : Batch Start!")
            system_version_info =  check_last_version()
            logging.info(system_version_info)
            #시스템 별 수행
            for info in system_version_info:
                attempt_count = 0
                while attempt_count < 3:
                    INDEX_NAME,SEED_CONT_VER,LOCAL_INDEX_VER,SEED_CONT_NAME = info[0],info[1],info[2],info[5]
                    logging.info(f"{INDEX_NAME} loop start!")
                    logging.info(f"{INDEX_NAME} cosmos check")
                    if 'media' in INDEX_NAME:
                        if SEED_CONT_VER != LOCAL_INDEX_VER:
                            logging.info(f"{INDEX_NAME} SEED_CONT_VER != LOCAL_INDEX_VER")
                            if cosmos_check(INDEX_NAME,SEED_CONT_VER,SEED_CONT_NAME):
                                verification_result = run_verification_for_qaset(INDEX_NAME, SEED_CONT_VER)
                                if verification_result == 1:
                                    update_last_version(VARIABLE.LOCAL,INDEX_NAME,SEED_CONT_VER)
                                else:
                                    rollback_seed_version_to_local(INDEX_NAME, LOCAL_INDEX_VER)
                                    history_insert("PIPELINE_ROLLBACK",INDEX_NAME, SEED_CONT_VER, 0)
                                    break

                        local_system_version_info = check_last_version(INDEX_NAME)[0]
                        logging.info(local_system_version_info)
                        INDEX_NAME,SEED_CONT_VER,LOCAL_INDEX_VER,INTEGRATION_INDEX_VER,SEARCH_CONT_VER = local_system_version_info[0],local_system_version_info[1],local_system_version_info[2],local_system_version_info[3],local_system_version_info[4]
                        logging.info(f"{INDEX_NAME} search_cont check")
                        if LOCAL_INDEX_VER != SEARCH_CONT_VER:
                            task = asyncio.create_task(transfer_data(INDEX_NAME,LOCAL_INDEX_VER))
                            await task
                            sync_status = local_search_cont_sync_check(INDEX_NAME,LOCAL_INDEX_VER)
                            if sync_status:update_last_version(VARIABLE.SEARCH_CONT,INDEX_NAME,LOCAL_INDEX_VER)
                            
                        for_checkallsystemsync_version_info =  check_last_version(INDEX_NAME)[0]
                        INDEX_NAME,SEED_CONT_VER,LOCAL_INDEX_VER,INTEGRATION_INDEX_VER,SEARCH_CONT_VER = for_checkallsystemsync_version_info[0],for_checkallsystemsync_version_info[1],for_checkallsystemsync_version_info[2],for_checkallsystemsync_version_info[3],for_checkallsystemsync_version_info[4]
                        if SEED_CONT_VER == SEARCH_CONT_VER:
                            logging.info(f"{INDEX_NAME} SEED_CONT_VER == SEARCH_CONT_VER, Can exit loop")
                            break
                    else:
                        if SEED_CONT_VER != LOCAL_INDEX_VER:
                            logging.info(f"{INDEX_NAME} SEED_CONT_VER != LOCAL_INDEX_VER")
                            if cosmos_check(INDEX_NAME,SEED_CONT_VER,SEED_CONT_NAME):
                                verification_result = run_verification_for_qaset(INDEX_NAME, SEED_CONT_VER)
                                if verification_result == 1:
                                    update_last_version(VARIABLE.LOCAL,INDEX_NAME,SEED_CONT_VER)
                                else:
                                    rollback_seed_version_to_local(INDEX_NAME, LOCAL_INDEX_VER)
                                    history_insert("PIPELINE_ROLLBACK",INDEX_NAME, SEED_CONT_VER, 0)
                                    break
                        local_system_version_info = check_last_version(INDEX_NAME)[0]
                        logging.info(local_system_version_info)
                        INDEX_NAME,LOCAL_INDEX_VER,INTEGRATION_INDEX_VER = local_system_version_info[0],local_system_version_info[2],local_system_version_info[3]
                        logging.info(f"{INDEX_NAME} integration check")
                        if LOCAL_INDEX_VER != INTEGRATION_INDEX_VER:
                            task = asyncio.create_task(migration(INDEX_NAME, INTEGRATION_INDEX_NAME, 100, LOCAL_INDEX_VER))
                            await task
                            
                            sync_status = check_local_integration_sync_status(INDEX_NAME, LOCAL_INDEX_VER)
                            if sync_status:
                                logging.info("Integration sync status: Successful")
                            else:
                                logging.info("Integration sync status: Failed")
                            if sync_status:
                                update_last_version(VARIABLE.INTEGRATION,INDEX_NAME,LOCAL_INDEX_VER)
                            
                        integration_system_version_info =  check_last_version(INDEX_NAME)[0]
                        INDEX_NAME,SEED_CONT_VER,LOCAL_INDEX_VER,INTEGRATION_INDEX_VER,SEARCH_CONT_VER = integration_system_version_info[0],integration_system_version_info[1],integration_system_version_info[2],integration_system_version_info[3],integration_system_version_info[4]
                        logging.info(f"{INDEX_NAME} search_cont check")
                        if INTEGRATION_INDEX_VER != SEARCH_CONT_VER:
                            task = asyncio.create_task(transfer_data(INDEX_NAME,LOCAL_INDEX_VER))
                            await task
                            sync_status = local_search_cont_sync_check(INDEX_NAME,LOCAL_INDEX_VER)
                            if sync_status:update_last_version(VARIABLE.SEARCH_CONT,INDEX_NAME,LOCAL_INDEX_VER)
                        for_checkallsystemsync_version_info =  check_last_version(INDEX_NAME)[0]
                        INDEX_NAME,SEED_CONT_VER,LOCAL_INDEX_VER,INTEGRATION_INDEX_VER,SEARCH_CONT_VER = for_checkallsystemsync_version_info[0],for_checkallsystemsync_version_info[1],for_checkallsystemsync_version_info[2],for_checkallsystemsync_version_info[3],for_checkallsystemsync_version_info[4]
                        if SEED_CONT_VER == SEARCH_CONT_VER:
                            logging.info(f"{INDEX_NAME} SEED_CONT_VER == SEARCH_CONT_VER, Can exit loop")
                            break
                    attempt_count += 1
                    logging.info(f"{INDEX_NAME} loop end!")
                
            logging.info(f"migration_function_trigger_{SYSTEM_LOCATION}: Batch End!")
    
    except Exception as e:
        trace = traceback.format_exception(type(e), e, e.__traceback__)
        error_message = "".join(trace)
        history_insert(system_name=SYSTEM_NAME, work_type='ERROR', version=CURRENT_VERSION, count=1, error=error_message) # Error History 
    finally:
        history_insert(system_name=SYSTEM_NAME, work_type='BATCH_END', version=CURRENT_VERSION, count=1)

    return func.HttpResponse(
        "This HTTP triggered function executed successfully. Pass a name in the query string or in the request body for a personalized response.",
        status_code=200
    )






@app.function_name(name=f"delete_function_trigger_{SYSTEM_LOCATION}")
@app.schedule(schedule="0 23 * * *", arg_name="deleteTimer", run_on_startup=False,
              use_monitor=False) 
async def timer_trigger(deleteTimer: func.TimerRequest) -> None:
    if deleteTimer.past_due:
        logging.info(f'delete_function_trigger_{SYSTEM_LOCATION} : The timer is past due!')
        
    try:
        CURRENT_TIME = datetime.now()
        CURRENT_VERSION = CURRENT_TIME.strftime('%y%m%d')
        SYSTEM_NAME = 'delete'
        history_insert(system_name=SYSTEM_NAME, work_type='BATCH', version=CURRENT_VERSION, count=1)
                    
        async with batch_lock:
            logging.info(f"delete_function_trigger_{SYSTEM_LOCATION} : Batch Start!")
            system_version_info =  check_delete_version()
            logging.info(system_version_info)
            system_last_version_info =  check_last_version()
            logging.info(system_last_version_info)
            tasks = []
            for info in system_version_info:
                tasks.append(asyncio.create_task(delete_old_versions_aisearch(info[0], info[2])))
                tasks.append(asyncio.create_task(delete_old_versions_cosmos(info[0], info[2])))
            for info in system_last_version_info:
                tasks.append(asyncio.create_task(delete_old_versions_cosmos_seed(info[0], info[2], info[5])))
            
            await asyncio.gather(*tasks)
            logging.info(f"delete_function_trigger_{SYSTEM_LOCATION} : Batch End!")
    
    except Exception as e:
        trace = traceback.format_exception(type(e), e, e.__traceback__)
        error_message = "".join(trace)
        history_insert(system_name=SYSTEM_NAME, work_type='ERROR', version=CURRENT_VERSION, count=1, error=error_message) # Error History 
    finally:
        history_insert(system_name=SYSTEM_NAME, work_type='BATCH_END', version=CURRENT_VERSION, count=1)
        
        
@app.function_name(name=f"http_delete_function_trigger_{SYSTEM_LOCATION}")
@app.route(route=f"http_delete_function_trigger_{SYSTEM_LOCATION}", auth_level=func.AuthLevel.ANONYMOUS)
async def HttpTrigger(req: func.HttpRequest) -> func.HttpResponse:            
    
    logging.info(f'delete_function_trigger_{SYSTEM_LOCATION} : Python HTTP trigger function processed a request.')
    try:
        CURRENT_TIME = datetime.now()
        CURRENT_VERSION = CURRENT_TIME.strftime('%y%m%d')
        SYSTEM_NAME = 'delete'
        history_insert(system_name=SYSTEM_NAME, work_type='BATCH', version=CURRENT_VERSION, count=1)
                    
        async with batch_lock:
            logging.info(f"delete_function_trigger_{SYSTEM_LOCATION} : Batch Start!")
            system_version_info =  check_delete_version()
            logging.info(system_version_info)
            system_last_version_info =  check_last_version()
            logging.info(system_last_version_info)
            tasks = []
            for info in system_version_info:
                tasks.append(asyncio.create_task(delete_old_versions_aisearch(info[0], info[2])))
                tasks.append(asyncio.create_task(delete_old_versions_cosmos(info[0], info[2])))
            for info in system_last_version_info:
                tasks.append(asyncio.create_task(delete_old_versions_cosmos_seed(info[0], info[2], info[5])))
            
            await asyncio.gather(*tasks)
            logging.info(f"delete_function_trigger_{SYSTEM_LOCATION} : Batch End!")
    
    except Exception as e:
        trace = traceback.format_exception(type(e), e, e.__traceback__)
        error_message = "".join(trace)
        history_insert(system_name=SYSTEM_NAME, work_type='ERROR', version=CURRENT_VERSION, count=1, error=error_message) # Error History 
    finally:
        history_insert(system_name=SYSTEM_NAME, work_type='BATCH_END', version=CURRENT_VERSION, count=1)        
        
    return func.HttpResponse(
        "This HTTP triggered function executed successfully. Pass a name in the query string or in the request body for a personalized response.",
        status_code=200
    )
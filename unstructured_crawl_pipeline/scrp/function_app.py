import azure.functions as func
import logging
import json
import sys,os
import os
from datetime import datetime
from utils.log_manager import LogManager
import traceback

sys.path.append(os.path.join(os.path.dirname(__file__), 'utils'))
sys.path.append(os.path.join(os.path.dirname(__file__), 'scrp'))
logging.basicConfig(level=logging.ERROR)
logging.getLogger("azure").setLevel(logging.WARNING)
logging.getLogger("azure.core.pipeline.policies.http_logging_policy").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

app = func.FunctionApp()
COSMOS_SEED_CONTAINER_NAME = os.environ['COSMOS_SEED_CONTAINER_NAME']
COSMOS_DB_NAME = os.environ['COSMOS_DB_NAME']
COSMOS_LEASE_CONTAINER_NAME = os.environ['COSMOS_LEASE_CONTAINER_NAME']

SYSTEM_NAME = os.environ['SYSTEM_NAME']
SYSTEM_LOCATION = os.environ['SYSTEM_LOCATION']
TIMER_CRON = os.environ['TIMER_CRON']
TIMER_CRON_HOUR = os.environ['TIMER_CRON_HOUR']

@app.function_name(name=f"{SYSTEM_NAME}_{SYSTEM_LOCATION}_CosmosDBTrigger")
@app.cosmos_db_trigger(arg_name="documents",
                       database_name=COSMOS_DB_NAME,
                       container_name=COSMOS_SEED_CONTAINER_NAME,
                       connection="cosmosrubiconkr_DOCUMENTDB",
                       lease_container_name=COSMOS_LEASE_CONTAINER_NAME,
                       lease_database_name=COSMOS_DB_NAME,
                       max_items_per_invocation=10, 
                       create_lease_container_if_not_exists=True)
async def cosmosdb_trigger(documents: func.DocumentList):
    try:
        from scrp.proc_scrp_cosmos import run_cosmos_scrp
        await LogManager.info(f"cosmos triggered count: {len(documents)}")
        for doc in documents:
            doc_data = json.loads(doc.to_json())
            if doc_data['next_action'] == True:
                await run_cosmos_scrp(doc_data)
        
    except Exception as e:
        await LogManager.exception(e)

# 긴급 배치 트리거
import subprocess
@app.function_name(name=f"{SYSTEM_NAME}_{SYSTEM_LOCATION}_HttpTrigger")
@app.route(route=f"{SYSTEM_NAME}_{SYSTEM_LOCATION}_HttpTrigger", auth_level=func.AuthLevel.ANONYMOUS)
async def HttpTrigger(req: func.HttpRequest, context: func.Context) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')
    
    try:
        from utils.proc_index_version import update_last_version, get_last_version, insert_history, WorkType, is_batch_running
        from scrp.proc_scrp_timer import run_scrp, get_seed_count
        from scrp.src.chrome import install_chrome
        LAST_VERSION = await get_last_version() # 정상 배치의 경우 6자리 날짜(ex. 250613), 긴급 배치의 경우 시,분 포함 10자리(ex. 2506131509)
        CURRENT_TIME = datetime.now()
        CURRENT_VERSION = CURRENT_TIME.strftime('%y%m%d%H%M') # 긴급 배치의 경우 시,분 포함
        
        await LogManager.info(f"Start http_trigger: batch time {CURRENT_TIME}, current version {CURRENT_VERSION}")
        
        # 배치가 동작 중인지 확인(가장 최근 history 가 work_type이 batch 이고, debug_count 가 1 이면 배치 동작 중, 현재 날짜의 버전만 확인)
        is_running = await is_batch_running(version=CURRENT_VERSION[:6])
        
        # 실행 중인 배치가 없는 경우 배치 동작
        if not is_running:
            
            # libcairo2-dev 설치(svg 처리)
            try:
                subprocess.run("apt-get update", shell=True, check=True)
                subprocess.run("apt-get install -y libcairo2-dev", shell=True, check=True)
            except subprocess.CalledProcessError as e:
                logging.warning(f"apt-get failed: {e}")

            chrome_path = "/usr/bin/google-chrome"
            if not os.path.exists(chrome_path):
                logging.warning(f"Chrome binary not found at {chrome_path}. Installing Chrome...")
                await install_chrome()
                # 설치 후 다시 확인
                if not os.path.exists(chrome_path):
                    await LogManager.error(f"Chrome installation failed. Binary not found at {chrome_path}", e )
            
            # 긴급 배치의 경우 무조건 실행 
            # 배치 프로세스
                    
            # 배치 실행 History, 정상 배치 동작 시 debug_count 1 로 insert
            await insert_history(work_type=WorkType.BATCH, version=CURRENT_VERSION, debug_count=1) # Batch History            
            success = await run_scrp((LAST_VERSION, CURRENT_VERSION))
            
            if success:
                # Seed 적재 완료 Version insert
                await update_last_version(CURRENT_VERSION)
                
                # Seed 적재 완료 History
                seed_count = await get_seed_count(CURRENT_VERSION) # 현재 Seed 수
                await insert_history(work_type=WorkType.SEED, version=CURRENT_VERSION, debug_count=seed_count) # Seed History 
            
                await LogManager.info(f'Python http trigger function executed. | status : {success}')                
            
            # 배치 예외, Recovery 시 배치가 이미 실행되었으면 실행 안함
            else:
                # 배치 실행 History, 배치 작업 없을 시(recovery) debug_count 0 로 insert
                await insert_history(work_type=WorkType.BATCH, version=CURRENT_VERSION, debug_count=0) # Batch History      

    except Exception as e:
        await LogManager.exception(e)
        # 배치 실행 오류 History
        trace = traceback.format_exception(type(e), e, e.__traceback__)
        error_message = "".join(trace)
        await insert_history(work_type=WorkType.ERROR, version=CURRENT_VERSION, debug_count=1, error_message=error_message) # Error History 
        

    return func.HttpResponse(
        "This HTTP triggered function executed successfully. Pass a name in the query string or in the request body for a personalized response.",
        status_code=200
    )
    
# # Daily batch
# # 한국 시간 오전 2시에 실행
@app.function_name(name=f"{SYSTEM_NAME}_{SYSTEM_LOCATION}_TimerTrigger")
@app.timer_trigger(schedule=TIMER_CRON, arg_name="mytimer", run_on_startup=False)
async def TimerTrigger(mytimer: func.TimerRequest) -> None:
    if mytimer.past_due:
        logging.info('The timer is past due!')
    from utils.log_manager import LogManager
    try:
        subprocess.run("apt-get update", shell=True, check=True)
        subprocess.run("apt-get install -y libcairo2-dev", shell=True, check=True)
    except subprocess.CalledProcessError as e:
        logging.warning(f"apt-get failed: {e}")

    try:
        from utils.proc_index_version import update_last_version, get_last_version, insert_history, WorkType,is_batch_running
        from scrp.proc_scrp_timer import run_scrp, get_seed_count
        from scrp.src.chrome import install_chrome
        from datetime import datetime, timedelta

        chrome_path = "/usr/bin/google-chrome"
        if not os.path.exists(chrome_path):
            logging.warning(f"Chrome binary not found at {chrome_path}. Installing Chrome...")
            await install_chrome()
            # 설치 후 다시 확인
            if not os.path.exists(chrome_path):
                await LogManager.error(f"Chrome installation failed. Binary not found at {chrome_path}", e )
        
        LAST_VERSION = await get_last_version() # 정상 배치의 경우 6자리 날짜(ex. 250613), 긴급 배치의 경우 시,분 포함 10자리(ex. 2506131509)
        CURRENT_TIME = datetime.now()
        CURRENT_HOUR = str(CURRENT_TIME.hour)
        
        # if CURRENT_HOUR < TIMER_CRON_HOUR: # Recovery 시간이 정상 배치 시간보다 빠른 경우, 동작하지 않도록 처리
        #     CURRENT_VERSION = (CURRENT_TIME - timedelta(days=1)).strftime('%y%m%d')
        # else : 
        #     CURRENT_VERSION = CURRENT_TIME.strftime('%y%m%d')   
        CURRENT_VERSION = CURRENT_TIME.strftime('%y%m%d')
        
        is_recovery = CURRENT_HOUR != TIMER_CRON_HOUR # 리커버리 여부
        
        await LogManager.info(f"Start timer_trigger: batch time {CURRENT_TIME}, current version {CURRENT_VERSION}")

        # 배치가 동작 중인지 확인(가장 최근 history 가 work_type이 batch 이고, debug_count 가 1 이면 배치 동작 중, 현재 날짜의 버전만 확인)
        is_running = await is_batch_running(version=CURRENT_VERSION[:6])
        
        # 실행 중인 배치가 없는 경우 배치 동작
        if not is_running:
                       
            # 배치 동작, 현재 버전 날짜 비교, 배치 날짜가 이전이면 동작 수행
            # 지난 버전이 긴급 배치 버전인 경우 정상 배치는 무조건 수행, 배치 날짜가 동일한 경우, 지난 버전이 긴급 배치이면 실행
            if (LAST_VERSION[:6] < CURRENT_VERSION) or (LAST_VERSION[:6] == CURRENT_VERSION and len(LAST_VERSION)>=10 and not is_recovery):

                await insert_history(work_type=WorkType.BATCH, version=CURRENT_VERSION, debug_count=1) # Batch History
                success = await run_scrp((LAST_VERSION, CURRENT_VERSION))

                if success:
                    await update_last_version(CURRENT_VERSION)
                    seed_count = await get_seed_count(CURRENT_VERSION) # 현재 Seed 수
                    await insert_history(work_type=WorkType.SEED, version=CURRENT_VERSION, debug_count=seed_count) # Seed History 
            else: 
                await insert_history(work_type=WorkType.BATCH, version=CURRENT_VERSION, debug_count=0) # Batch History
               
    except Exception as e:
        await LogManager.exception(e)
        trace = traceback.format_exception(type(e), e, e.__traceback__)
        error_message = "".join(trace)
        await insert_history(work_type=WorkType.ERROR, version=CURRENT_VERSION, debug_count=0, error_message=error_message) # Error History 
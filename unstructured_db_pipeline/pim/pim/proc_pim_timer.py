import os
from utils.task_info import TaskType,TaskStatus,SeedData
from utils.log_manager import LogManager
from utils.proc_common import change_status
from pim.proc_pim_common import PimSeedContainer
from pim.src.database.fetch import fetch_new_codes, fetch_old_codes
from pim.proc_pim import pim_main
from utils.log_manager import LogManager
from utils.data_cosmos import WorkerLogContainer
from utils.data_search import SearchService
from utils.proc_index_version import sampling_qaset, insert_verification_row
import logging

SYSTEM_NAME = os.environ['SYSTEM_NAME']
SYSTEM_LOCATION = os.environ.get("SYSTEM_LOCATION")
QSET_PERCENT = int(os.environ.get("QSET_PERCENT"))
QSET_MIN = int(os.environ.get("QSET_MIN"))

async def run_pim(version):
    await LogManager.info(f"start run_pim {SYSTEM_LOCATION}")
    _, current_version = version
    new_product_codes = await fetch_new_codes() # 최신 3일 모델코드
    old_product_codes = await fetch_old_codes() # 그외 모델 코드
    
    logging.info(f"신규 적재 대상 모델:{len(new_product_codes)}")
    logging.info(f"중복 적재 대상 모델:{len(old_product_codes)}")
    
    ref_data_list, loaded_list = await pim_main(version, new_product_codes, old_product_codes)

    # 중복 데이터 업로드
    try:
        await LogManager.info(f"중복 데이터 {len(loaded_list)}건 적재 시작")
        await SearchService.upload_batch(loaded_list, 100)
    except Exception as e:
        await LogManager.error(f"중복 데이터 업로드 오류 : {str(e)}")
        
    # Seed 적재
    if ref_data_list:
        indices_to_flag = await sampling_qaset(data_list=ref_data_list, sampling_rate=QSET_PERCENT  * 0.01, min_sample=QSET_MIN)
        await LogManager.info(f"신규 데이터 {len(ref_data_list)}건 Seed 적재 시작")
        async with WorkerLogContainer() as log_cosmos:
            await change_status(SYSTEM_NAME,TaskStatus.IN_PROGRESS,TaskType.DEFAULT)
            try:
                for i, seed in enumerate(ref_data_list):
                    # 4. 현재 인덱스가 플래그 대상인지 확인하여 플래그 값 설정
                    is_flagged = i in indices_to_flag
                    seed.qset_flag = is_flagged
                    async with PimSeedContainer() as cosmos:
                        await cosmos.upsert(seed)
                await LogManager.info("Seed container 적재 완료")     
                await change_status(SYSTEM_NAME,TaskStatus.COMPLETED,TaskType.DEFAULT)
                return True        
            except Exception as e:
                await LogManager.exception(e,"Seed 적재 오류")
                await change_status(SYSTEM_NAME,TaskStatus.ERROR,TaskType.DEFAULT)
                return False
    else: 
        await LogManager.info(f"신규 데이터가 없어 과거 데이터 검증 셋 추가") 
        indices_to_flag = await sampling_qaset(data_list=loaded_list, sampling_rate=QSET_PERCENT  * 0.01, min_sample=QSET_MIN)
        # qset 대상일 경우 검증 셋 삽입
        try:
            for i, index in enumerate(loaded_list):
                is_sampled = i in indices_to_flag
                if is_sampled:
                    await insert_verification_row(
                        system_name= index.system_name, 
                        version= index.version,
                        cat1= index.category1,
                        cat2= index.category2,
                        cat3= index.category3,
                        model_code=index.model_code[0], 
                        chunk_text = index.semantic_chunk,
                        )
        except Exception as e:
            await LogManager.info(f"qset insert Error : {str(e)}")
        # 신규 데이터가 없는 경우 빈 Seed 적재
        try:
            async with PimSeedContainer() as cosmos:
                await cosmos.upsert(
                    SeedData(
                        system_name = SYSTEM_NAME,
                        version = current_version,
                        status = TaskStatus.COMPLETED,
                        next_action = False
                        )
                )
            return True
        except Exception as e:
            await LogManager.exception(e,"Seed 적재 오류")
            return False


async def get_seed_count(version):
    async with PimSeedContainer() as cosmos:
        filter = {"system_name": SYSTEM_NAME, 
                "version": version}
        select_fields = ['id']
        data = await cosmos.find(filters=filter, select_fields=select_fields)
        return len(data)        
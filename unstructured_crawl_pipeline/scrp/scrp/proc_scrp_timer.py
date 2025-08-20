import os
from utils.task_info import TaskType,TaskStatus,SeedData
from utils.log_manager import LogManager
from utils.proc_common import change_status
from scrp.proc_scrp_common import ScrpSeedContainer
from src.modules.fetch import fetch_all_page_config
from scrp.proc_scrp import scrp_main
from utils.log_manager import LogManager
from utils.data_cosmos import WorkerLogContainer
from utils.data_search import SearchService
from utils.proc_index_version import sampling_qaset, insert_verification_row

SYSTEM_NAME = os.environ['SYSTEM_NAME']
SYSTEM_LOCATION = os.environ.get("SYSTEM_LOCATION")
QSET_PERCENT = int(os.environ.get("QSET_PERCENT"))
QSET_MIN = int(os.environ.get("QSET_MIN"))

async def run_scrp(version):
    await LogManager.info(f"start run_scrp {SYSTEM_LOCATION}")
    _, current_version = version
    pages = await fetch_all_page_config()
    ref_data_list, loaded_list = await scrp_main(version, pages)

    # 중복 데이터 업로드
    try:
        await SearchService.upload_batch(loaded_list, 300)
    except Exception as e:
        await LogManager.info(f"Index Upload Error : {str(e)}")

    if ref_data_list:
        indices_to_flag = await sampling_qaset(data_list=ref_data_list, sampling_rate=QSET_PERCENT  * 0.01, min_sample=QSET_MIN)

        async with WorkerLogContainer() as log_cosmos:
            await change_status(SYSTEM_NAME, TaskStatus.IN_PROGRESS, TaskType.DEFAULT)
            try:
                await LogManager.info(f"Seed container 신규 데이터 적재 시작 : {len(ref_data_list)}")
                # 3. enumerate를 사용하여 인덱스와 데이터를 함께 순회
                for i, ref_data in enumerate(ref_data_list):
                    # 4. 현재 인덱스가 플래그 대상인지 확인하여 플래그 값 설정
                    is_flagged = i in indices_to_flag
                    seed = SeedData(
                        system_name = SYSTEM_NAME,
                        version = current_version,
                        ref_data = ref_data,
                        qset_flag = is_flagged  # 5. SeedData 객체에 플래그 추가
                    )
                    async with ScrpSeedContainer() as cosmos:
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
        indices_to_flag = await sampling_qaset(data_list=loaded_list, sampling_rate=QSET_PERCENT * 0.01, min_sample=QSET_MIN)
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
                        model_code=None, 
                        chunk_text = index.semantic_chunk,
                        )
        except Exception as e:
            await LogManager.info(f"qset insert Error : {str(e)}")
            
        # 신규 데이터가 없는 경우 빈 Seed 적재
        try:
            async with ScrpSeedContainer() as cosmos:
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
    async with ScrpSeedContainer() as cosmos:
        filter = {"system_name": SYSTEM_NAME, 
                "version": version}
        select_fields = ['id']
        data = await cosmos.find(filters=filter, select_fields=select_fields)
        return len(data)

import asyncio
if __name__=="__main__":
    asyncio.run(run_scrp(("250722","250723")))
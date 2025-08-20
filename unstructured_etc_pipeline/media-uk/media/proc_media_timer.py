import os
from utils.task_info import TaskType,TaskStatus,SeedData
from utils.log_manager import LogManager
from utils.proc_common import change_status
from media.proc_media_common import MediaSeedContainer
from media.proc_media import media_main
from utils.log_manager import LogManager
from utils.data_cosmos import WorkerLogContainer
from utils.data_search import SearchService
from media.workers._01_embedded_image import process_image_embedding
from media.workers._02_media_dup import process_media_duplicate
from media.workers._03_image_process import process_image_check
from utils.proc_index_version import sampling_qaset, insert_verification_row

SYSTEM_NAME = os.environ['SYSTEM_NAME']
SYSTEM_LOCATION = os.environ.get("SYSTEM_LOCATION")
QSET_PERCENT = int(os.environ.get("QSET_PERCENT"))
QSET_MIN = int(os.environ.get("QSET_MIN"))

async def run_media(version):
    await LogManager.info(f"start run_pim_media {SYSTEM_LOCATION}")
    _, current_version = version
    # 이미지 임베딩 처리
    await LogManager.info(f"start run image_embedding {SYSTEM_LOCATION}")
    await process_image_embedding()
    # 이미지 유사성 체크 및 중복 제거, 병합
    await LogManager.info(f"start run check duplicate image {SYSTEM_LOCATION}")
    await process_media_duplicate()
    # pim 이미지 처리 후 db 저장
    await LogManager.info(f"start run db upsert {SYSTEM_LOCATION}")
    await process_image_check(ver=version)

    # 저장된 pim 이미지 url로 ref_data 생성
    ref_data_list, loaded_list = await media_main(version)

    # 중복 데이터 업로드
    try:
        await LogManager.info(f"중복 데이터 {len(loaded_list)}건 적재 시작")
        await SearchService.upload_batch(loaded_list, 100)
    except Exception as e:
        await LogManager.error(f"중복 데이터 업로드 오류 : {str(e)}")
        
    # Seed 적재
    if ref_data_list:
        indices_to_flag = await sampling_qaset(data_list=ref_data_list, sampling_rate=QSET_PERCENT *0.01, min_sample=QSET_MIN)            
        await LogManager.info(f"신규 데이터 {len(ref_data_list)}건 Seed 적재 시작")
        async with WorkerLogContainer() as log_cosmos:
            await change_status(SYSTEM_NAME,TaskStatus.IN_PROGRESS,TaskType.DEFAULT)
            try:
                for i, ref_data in enumerate(ref_data_list):
                    # 4. 현재 인덱스가 플래그 대상인지 확인하여 플래그 값 설정
                    is_flagged = i in indices_to_flag
                    seed = SeedData(
                        system_name = SYSTEM_NAME,
                        version = current_version,
                        ref_data = ref_data,
                        qset_flag = is_flagged  # 5. SeedData 객체에 플래그 추가
                    )

                    async with MediaSeedContainer() as cosmos:
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
                        model_code=index.model_code[0], 
                        chunk_text = ref_data.chunk,   
                        )
        except Exception as e:
            await LogManager.info(f"qset insert Error : {str(e)}")
        # 신규 데이터가 없는 경우 빈 Seed 적재
        try:
            async with MediaSeedContainer() as cosmos:
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
    async with MediaSeedContainer() as cosmos:
        filter = {"system_name": SYSTEM_NAME, 
                "version": version}
        select_fields = ['id']
        data = await cosmos.find(filters=filter, select_fields=select_fields)
        return len(data)        
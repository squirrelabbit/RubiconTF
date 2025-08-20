import os
from enum import Enum
from utils.data_postgres import DBManager
from utils.common import get_secret_from_key_vault
import hashlib
from utils.log_manager import LogManager
from pim.proc_pim_common import PimSeedContainer
import random

AZURE_OPENAI_EMBEDDING_API_VERSION = os.environ.get("AZURE_OPENAI_EMBEDDING_API_VERSION")
AZURE_OPENAI_EMBEDDING_ENDPOINT = os.environ.get("AZURE_OPENAI_EMBEDDING_ENDPOINT")
AZURE_OPENAI_EMBEDDING_SECRET_NAME = os.environ.get("AZURE_OPENAI_EMBEDDING_SECRET_NAME")
AZURE_OPENAI_EMBEDDING_API_KEY = get_secret_from_key_vault(AZURE_OPENAI_EMBEDDING_SECRET_NAME)
# AZURE_OPENAI_EMBEDDING_API_KEY = os.environ["AZURE_OPENAI_EMBEDDING_API_KEY"]
AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME = os.environ.get("AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME")


AZURE_SEARCH_ENDPOINT=os.environ.get("AZURE_SEARCH_ENDPOINT")
AZURE_SEARCH_SECRET_NAME = os.environ.get("AZURE_SEARCH_SECRET_NAME")
AZURE_SEARCH_API_KEY = get_secret_from_key_vault(AZURE_SEARCH_SECRET_NAME)
# AZURE_SEARCH_API_KEY=os.environ.get("AZURE_SEARCH_API_KEY")
AZURE_SEARCH_API_VERSION= os.environ.get("AZURE_SEARCH_API_VERSION")
SYSTEM_NAME = os.environ['SYSTEM_NAME']
SYSTEM_LOCATION = os.environ['SYSTEM_LOCATION']

PGDB_INDEX_TABLE_NAME = os.environ.get('PGDB_INDEX_TABLE_NAME')
PGDB_VERSION_INFO_TABLE_NAME = os.environ['PGDB_VERSION_INFO_TABLE_NAME']
PGDB_VERSION_HISTORY_TABLE_NAME = os.environ['PGDB_VERSION_HISTORY_TABLE_NAME']
PGDB_QSET_TABLE_NAME = os.environ['PGDB_QSET_TABLE_NAME']

class WorkType(str, Enum):
    BATCH = "BATCH"
    SEED = "SEED"
    LOCAL = "LOCAL"
    INTEGRATION = "INTEGRATION"
    SEARCH = "SEARCH"
    ERROR = "ERROR"
    

# 지난 배치 버전, Search Cont 반영까지 완료된 버전전
async def get_last_version():
    async with DBManager(db_name='cloocusdb') as db:
        
        query = f"""SELECT integration_last_version
                    FROM {PGDB_VERSION_INFO_TABLE_NAME} 
                    WHERE system_name='{SYSTEM_NAME}';"""
        result = await db.fetch(query)
        
        return result[0]['integration_last_version']

async def update_last_version(version):
    async with DBManager(db_name='cloocusdb') as db:
        query = f"""UPDATE {PGDB_VERSION_INFO_TABLE_NAME} 
                    SET 
                    seed_cont_last_version = '{version}', 
                    seed_cont_last_updated = NOW()
                    WHERE system_name='{SYSTEM_NAME}';"""
        await db.update(query)

# history 삽입
async def insert_history(work_type: WorkType, version, debug_count, error_message=None):
    async with DBManager(db_name='cloocusdb') as db:  
        query = f"""INSERT INTO
        {PGDB_VERSION_HISTORY_TABLE_NAME} (system_name, work_type, version, debug_count, error_message)
        VALUES ($1, $2, $3, $4, $5);
        """ 
        await db.update(query, SYSTEM_NAME, work_type.value, str(version), debug_count, error_message)
        
# 현재 동작 중인 배치 확인, 가장 최근 history가 batch이고 debug_count 가 1인지 확인        
async def is_batch_running(version):
    async with DBManager(db_name='cloocusdb') as db:  
        query = f"""SELECT work_type, version, debug_count, updated
        FROM {PGDB_VERSION_HISTORY_TABLE_NAME}
        WHERE 
            system_name='{SYSTEM_NAME}' 
            AND version like '{version}%' 
        ORDER BY updated DESC
        LIMIT 1;
        """             
        result = await db.fetch(query)
        if not result:
            return False
        
        work_type = result[0]['work_type']
        debug_count = result[0]['debug_count']
        last_version = result[0]['version']
        
        if work_type == WorkType.BATCH.value and debug_count == 1:
            await LogManager.info(f"[BATCH CHECK] 최근 작업: BATCH (debug_count=1, version={last_version}) → 현재 배치 실행 중")
            return True
        elif work_type == WorkType.SEED.value:
            async with PimSeedContainer() as cosmos:
                filter = {"version": last_version}
                results = await cosmos.find(filters=filter)
                for seed in results:
                    if seed['next_action'] is True:
                        await LogManager.info(f"[BATCH CHECK] 최근 작업: SEED (version={last_version}) → 시드 작업 실행 중")
                        return True
        await LogManager.info(f"[BATCH CHECK] 현재 실행 중인 배치/시드 작업 없음 → 신규 작업 수행 가능")
        return False

INSERT_QA = f"""
        INSERT INTO {PGDB_QSET_TABLE_NAME} (
            filter_system_name,
            filter_version,
            filter_category1,
            filter_category2,
            filter_category3,
            filter_modelcode,
            index_verification_value,
            index_verification_original_value,
            verification_inserted,
            verification_executed_flag   -- 기본 0
        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8, NOW(), 0)
"""
            
async def insert_verification_row(
    system_name: str,
    version: str,
    cat1: str,
    cat2: str,
    cat3: str,
    model_code: str | None,
    chunk_text: str,
) -> None:
    """
    pipeline_verification_qaset 테이블에 한 행 INSERT.

    - index_verification_value : chunk_text SHA-256 해시
    - verification_inserted    : NOW()
    - verification_executed_flag : false
    """
    # 1) 해시 생성
    ver_hash = hashlib.sha256(chunk_text.encode("utf-8")).hexdigest()

    # 3) 실행
    try:
        async with DBManager(db_name="cloocusdb") as db:
            await db.update(
                INSERT_QA,
                system_name,
                version,
                cat1,
                cat2,
                cat3,
                model_code,
                ver_hash,
                chunk_text,
            )
        await LogManager.info(
            f"[QA] verification row inserted | sys={system_name}, ver={version}"
        )
    except Exception as ex:
        await LogManager.error(f"[QA] insert failed: {ex}")    

async def sampling_qaset(data_list, sampling_rate, min_sample):
    data_count = len(data_list)
    num_to_flag = int(len(data_list) * sampling_rate)
    # 데이터 개수에 따라 플래그를 지정할 인덱스 목록을 결정
    if data_count <= min_sample:
        # 최소 샘플 수 이하이면 모든 인덱스를 플래그 대상으로 지정
        indices_to_flag = set(range(data_count))
        await LogManager.info(f"데이터가 {min_sample}건 이하여서 모든 데이터에 플래그를 설정합니다.")
    elif num_to_flag <= min_sample:
        # 계산된 갯수가 최소값 보다 작으면 최소값 지정
        indices_to_flag = set(random.sample(range(len(data_list)), min_sample))
    else:
        # 최소값 초과이면 샘플 비율에 맞게게 랜덤 샘플링
        indices_to_flag = set(random.sample(range(len(data_list)), num_to_flag))
    await LogManager.info(f"데이터가 {min_sample}건을 초과하여 {len(indices_to_flag)}건에 랜덤 플래그를 설정합니다.")    
    
    await LogManager.info(f"검증 대상 데이터 {data_count}건 중 {len(indices_to_flag)}건 플래그 지정")
    
    return indices_to_flag
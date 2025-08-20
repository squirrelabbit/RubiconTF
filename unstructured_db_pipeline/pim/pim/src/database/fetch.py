import logging
from utils.data_postgres import DBManager
from src.config.settings import DATABASE

logger = logging.getLogger("app_logger")

async def fetch_all_codes():
    """ 테이블에서 모든 데이터를 가져오는 비동기 함수 """
    query = f"SELECT * FROM {DATABASE['table_name']} order by model_code;"
    async with DBManager(db_name=DATABASE['database']) as db:
        try:
            return await db.fetch(query)
        except Exception as e:
            raise Exception(f"DB에서 모델 코드 가져오기 실패: {e}")
                
async def fetch_new_codes():
    """ 테이블에서 최신 3일 데이터를 가져오는 비동기 함수 """
    
    query = f"""
        SELECT *
        FROM {DATABASE['table_name']}
        WHERE DATE(update_date) IN (
            SELECT DISTINCT DATE(update_date)
            FROM {DATABASE['table_name']}
            ORDER BY DATE(update_date) DESC
            LIMIT 3
        )
        ORDER BY update_date DESC;
    """

    async with DBManager(db_name=DATABASE['database']) as db:
        try:
            return await db.fetch(query)
        except Exception as e:
            raise Exception(f"DB에서 모델 코드 가져오기 실패: {e}")

async def fetch_old_codes():
    """ 테이블에서 최신 3일 데이터를 가져오는 비동기 함수 """
    
    query = f"""
        SELECT *
        FROM {DATABASE['table_name']}
        WHERE DATE(update_date) NOT IN (
            SELECT DISTINCT DATE(update_date)
            FROM {DATABASE['table_name']}
            ORDER BY DATE(update_date) DESC
            LIMIT 3
        )
        ORDER BY update_date DESC;
    """

    async with DBManager(db_name=DATABASE['database']) as db:
        try:
            return await db.fetch(query)
        except Exception as e:
            raise Exception(f"DB에서 모델 코드 가져오기 실패: {e}")
        
async def fetch_data_by_code(model_code:str):
    query = f"""
        SELECT *
        FROM {DATABASE['table_name']}
        WHERE model_code ='{model_code}';
    """
    async with DBManager(db_name=DATABASE['database']) as db:
        try:
            return await db.fetch(query)
        except Exception as e:
            raise Exception(f"DB에서 모델 코드 가져오기 실패: {e}")
        
async def get_bu_by_mdl_name(model_name: str):
    """ 특정 모델명에 해당하는 business_unit을 가져오는 비동기 함수 """
    query = f"SELECT business_unit FROM rubicon_data_product_category WHERE model_name = $1;"
    async with DBManager(db_name='alpha') as db:
        try:
            result = await db.fetch(query, model_name)
            return result[0] if result else None
        except Exception as e:
            raise Exception(f"DB에서 부서명 가져오기 실패: {e}")
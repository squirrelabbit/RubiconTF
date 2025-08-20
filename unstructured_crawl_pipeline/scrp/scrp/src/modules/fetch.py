import logging
from utils.data_postgres import DBManager
from src.config.settings import DATABASE

logger = logging.getLogger("app_logger")

async def fetch_all_page_config():
    """ 테이블에서 모든 데이터를 가져오는 비동기 함수 """
    query = (
        f"""
            SELECT * 
            FROM {DATABASE['table_name']}
            WHERE is_display = 1 
            order by id;
        """
    )
    async with DBManager(db_name=DATABASE['database']) as db:
        try:
            return await db.fetch(query)
        except Exception as e:
            raise Exception(f"DB에서 모델 코드 가져오기 실패: {e}")
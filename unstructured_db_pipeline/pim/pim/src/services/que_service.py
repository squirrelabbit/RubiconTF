from src.services.crawl_service import crawl_static_contents
from src.modules.driver import init_driver
import logging
from threading import Lock

logger = logging.getLogger("app_logger")
lock = Lock()

async def process_queue(row):
    """Queue 처리 로직"""
    if not isinstance(row, dict):
        row = dict(row)
    model_code = row.get("model_code")
    driver = init_driver()
    try:
        # 크롤링 로직 실행
        result_data =[]
        crawl_item_list = await crawl_static_contents(row, driver)
        if crawl_item_list:
            for feature_index in crawl_item_list:
                json_data = feature_index.to_upload_sch_data()
                result_data.append(json_data)
    
    except Exception as e:
        logger.error(f"Error during crawling for {model_code}: {e}")

    return result_data        
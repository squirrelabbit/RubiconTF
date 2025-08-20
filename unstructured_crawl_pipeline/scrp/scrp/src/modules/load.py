from selenium.common.exceptions import TimeoutException, WebDriverException
import logging
import time
from utils.log_manager import LogManager

logger = logging.getLogger("app_logger")

async def load_page_with_retry(driver, url, retries=3, backoff_factor=2):
    for attempt in range(retries):
        try:
            logger.info(f"Attempting to load page: {url} (Attempt {attempt + 1}/{retries})")
            driver.get(url)
            # driver.execute_script("""
            #     var elements = document.querySelectorAll('.blind');
            #     elements.forEach(el => el.remove());
            # """)
            return  # 성공 시 함수 종료
        except (TimeoutException, WebDriverException, ConnectionError) as e:
            logger.warning(f"Timeout occurred while loading {url}: {e} (Attempt {attempt + 1}/{retries})")
            if attempt == retries - 1:
                await LogManager.error(f"Failed to load page after {retries} retries: {url}")
                raise  # 모든 재시도가 실패하면 예외 발생
            time.sleep(backoff_factor ** attempt)  # 지수 백오프 적용
        except Exception as e:
            logger.error(f"Unexpected error while loading {url}: {e}")
            raise
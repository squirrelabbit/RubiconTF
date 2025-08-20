from bs4 import BeautifulSoup
from src.modules.chunk_processor import process_content
import logging
from urllib.parse import urljoin

logger = logging.getLogger("app_logger")

async def crawl_static_contents(row, driver):
    if row.get("display_status") =="no":
        return None
    model_code = row.get("model_code")
    url =urljoin("https://www.samsung.com",row.get("product_url"))
    try:
        driver.get(url)
    except Exception as e:
        logger.error(f"Failed to load page {url}: {e}")
        return []
    
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    
    def is_top_level(tag):
        if not tag.has_attr('class'):
            return False
        if not any('feature-benefit' in cls or 'multi-feature' in cls or 'features' in cls for cls in tag['class']):
            return False
        parent = tag.find_parent(lambda p: p.has_attr('class') and
                                any('feature-benefit' in cls or 'multi-feature' in cls or 'features' in cls for cls in p['class']))
        return parent is None
    
    candidates = soup.select('[class*="feature-benefit"], [class*="multi-feature"], [class*="features"]')
    elements = [tag for tag in candidates if is_top_level(tag)]
    
    if not elements:
        logger.warning(f"No top-level elements found with class containing 'feature-benefit', 'multi-feature', or 'features' for model {model_code}.")
        return []
    
    merged_content = "".join(str(el) for el in elements)
    return await process_content(merged_content, row)
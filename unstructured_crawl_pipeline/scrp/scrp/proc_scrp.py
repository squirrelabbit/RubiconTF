import os
from scrp.proc_scrp_common import ScrpSearchContainer,ScrpSearch, ScrpRefData
from tqdm import tqdm
from src.modules.driver import init_driver
from src.modules.process_crawl import process_page, process_list_page
from scrp.src.main import load_page_with_retry
from scrp.common_utils import generate_id
from utils.log_manager import LogManager

SYSTEM_NAME = os.environ['SYSTEM_NAME']

async def scrp_main(version,pages):
    result_data = []
    loaded_list = []
    ref_data_list = []
    last_version, current_version = version
    
    driver = init_driver()

    try:
        for page in tqdm(pages, desc="Processing Pages", unit="page"):
            page = dict(page)
            url = page["url"]
            # 페이지 로딩을 재시도 메서드 호출
            await load_page_with_retry(driver, url)
            # 페이지 처리
            if page["name"] == "FAQ":
                result_data.extend(await process_list_page(driver, page, url))
            else:
                result_data.extend(await process_page(driver, page, url))
                
            # print(result_data[0]["chunk"])
    finally:        
        driver.quit()
        
    duplicate_count = 0

    if result_data:
        for result in result_data:
            ## 기존 데이터 중복 여부 확인
            async with ScrpSearchContainer() as cosmos:
                filter = {"system_name": SYSTEM_NAME, 
                        "version": last_version, 
                        "blob_path": result.get("blob_path", ""),
                        "category1": result.get("category1", ""),
                        "category2": result.get("category2", ""), 
                        "semantic_chunk": result.get("semantic_chunk", ""),
                        }
                duplicate_data = await cosmos.find(filters=filter)
                if duplicate_data:
                    for item in duplicate_data:
                        index = ScrpSearch(**item)
                        index.version = current_version
                        index = generate_id(index)
                        loaded_list.append(index)
                        duplicate_count+=1
                else:
                    ref_data_list.append(ScrpRefData(**result))
        await LogManager.info(f"중복 데이터 : {duplicate_count}건")
        await LogManager.info(f"신규 Ref 데이터 : {len(ref_data_list)}건")
        
    return ref_data_list, loaded_list
from src.services.row_service import process_row_async
from src.services.que_service import process_queue
from pim.proc_pim_common import PimSearchContainer, PimSearch
from utils.task_info import SeedData
from utils.log_manager import LogManager
from pim.common_utils import generate_id, generate_original_id
from tqdm import tqdm
import os
import asyncio
from tqdm.asyncio import tqdm_asyncio

SYSTEM_NAME = os.environ['SYSTEM_NAME']

async def pim_main(version, new_product_codes, old_product_codes):
    seeds_to_index = []
    duplicate_index=[]
    last_version, current_version = version
    
    for model_code in tqdm(new_product_codes, desc="Processing Models"):
        ## api 호출하여 데이터 생성
        api_results = await process_row_async(model_code)
        if api_results:
            for ref in api_results:
                seed = SeedData(
                    system_name=SYSTEM_NAME,
                    version=current_version,
                    ref_data=ref,
                    ref_source="API"
                )
                seeds_to_index.append(seed) 
        ## api에 데이터가 없는경우 크롤링으로 데이터 생성
        else:
            crawl_results = await process_queue(model_code)
            if crawl_results:
                for ref in crawl_results:
                    seed = SeedData(
                        system_name=SYSTEM_NAME,
                        version=current_version,
                        ref_data=ref,
                        ref_source="CRAWL"
                    )
                    seeds_to_index.append(seed) 
    
    semaphore = asyncio.Semaphore(20)  # 동시에 최대 20개만 처리
    async def process_row_limited(row):
        async with semaphore:
            return await process_row(row)

    async def process_row(model_code):
       async with PimSearchContainer() as cosmos:
            query = """
            SELECT * FROM c
            WHERE c.system_name = @system_name
            AND c.version = @version
            AND ARRAY_CONTAINS(c.model_code, @model_code)
            """
            params = [
                {"name": "@system_name", "value": SYSTEM_NAME},
                {"name": "@version", "value": last_version},
                {"name": "@model_code", "value": model_code.get("model_code")}
            ]
            container = await cosmos.get_container()
            existing_docs = [doc async for doc in container.query_items(query=query, parameters=params)]
            if existing_docs:
                for doc in existing_docs:
                    index = PimSearch(**doc)
                    index.version = current_version
                    index = generate_id(index)
                    if not index.original_id:
                        index = generate_original_id(index)
                    duplicate_index.append(index)
            return duplicate_index
    
    tasks = [process_row_limited(model_code) for model_code in old_product_codes]
    processed = []
    for coro in tqdm_asyncio.as_completed(tasks, desc="Processing rows", total=len(tasks)):
        duplicate_index = await coro
        processed.append(duplicate_index)
    
    # 나눠 담기
    await LogManager.info(f"중복 데이터 : {len(duplicate_index)}건")
    await LogManager.info(f"신규 Ref 데이터 : {len(seeds_to_index)}건")
        
    return seeds_to_index, duplicate_index
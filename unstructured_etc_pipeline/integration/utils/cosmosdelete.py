import logging
from azure.cosmos import exceptions, PartitionKey
from azure.cosmos.aio import CosmosClient as AsyncCosmosClient
import os
import asyncio
import time
from utils.dbsearch import history_insert
import utils.constants as VARIABLE
from utils.common import get_secret_from_key_vault

COSMOS_DB_SECRET_NAME = os.environ.get("COSMOS_DB_SECRET_NAME")
COSMOS_KEY = get_secret_from_key_vault(COSMOS_DB_SECRET_NAME)
COSMOS_ENDPOINT = os.getenv("COSMOS_ENDPOINT")
DATABASE_NAME = os.getenv("DATABASE_NAME")
SEARCH_CONTAINER_NAME = os.getenv("SEARCH_CONTAINER_NAME")


async def delete_item(container, item_id):
    try:
        await container.delete_item(item_id, partition_key=item_id)
        return 1
    except Exception as e:
        return 0

# async def delete_all_items(container, system_name, version=None, work_type="search", batch_size=1000):
#     version_filter = "AND NOT IS_DEFINED(c.version)" if version is None else "AND c.version = @version"
#     query = f"SELECT c.id FROM c WHERE c.system_name = @system_name {version_filter}"
#     parameters = [{"name": "@system_name", "value": system_name}]
#     if version is not None:
#         parameters.append({"name": "@version", "value": version})
#     completed_count = 0
#     total_items_to_delete = 0
#     continuation_token = None
#     start_time = time.time()
    
#     # 배치로 항목을 가져와 삭제하는 루프
#     while True:
#         items_to_delete = []
#         try:
#             # 1000개씩 배치로 항목 가져오기
#             query_iterator = container.query_items(
#                 query=query,
#                 parameters=parameters,
#                 max_item_count=batch_size
#             ).by_page(continuation_token=continuation_token)
#             # 응답에서 항목을 비동기적으로 가져오기
#             page_results = await anext(query_iterator)
#             continuation_token = query_iterator.continuation_token
#             items_to_delete = [item async for item in page_results]
            
#         except Exception as e:
#             logging.error(f"항목 쿼리 실패: {str(e)}")
#             # break # 오류 발생 시 루프 종료
#         if not items_to_delete:
#             logging.info(f"[{system_name}] 버전 {version or 'undefined'} 삭제 대상 없음")
#             break # 더 이상 삭제할 항목이 없으면 루프 종료
#         total_items_to_delete += len(items_to_delete)
        
#         # 가져온 배치 삭제
#         tasks = [delete_item(container, item["id"]) for item in items_to_delete]
#         completed_in_batch = sum(await asyncio.gather(*tasks))
#         completed_count += completed_in_batch
#         logging.info(f"[{system_name}] 버전 {version or 'undefined'}: 배치 {len(items_to_delete)}건 중 {completed_in_batch}건 삭제 완료")
#         if not continuation_token:
#             break # 더 이상 페이지가 없으면 루프 종료
    
#     elapsed = time.time() - start_time
#     logging.info(f"[{system_name}] 버전 {version or 'undefined'}: 총 {completed_count}/{total_items_to_delete}건 완료, {elapsed:.2f}s 소요")
#     work_type_code = VARIABLE.WORK_TYPE_SEED_DELETE if work_type == "seed" else VARIABLE.WORK_TYPE_SEARCH_DELETE
#     if completed_count > 0:
#         history_insert(work_type_code, system_name, version or "undefined", completed_count)
        
        
        
# async def delete_all_items(container, system_name, version=None, work_type="search"):
#     # 유지버전 쿼리
#     if version is None:
#         version_filter = "AND NOT IS_DEFINED(c.version)"
#     else:
#         version_filter = "AND c.version = @version"
#     query = f"SELECT c.id FROM c WHERE c.system_name = @system_name {version_filter}"
#     parameters = [{"name": "@system_name", "value": system_name}]
#     if version is not None:
#         parameters.append({"name": "@version", "value": version})
#     items = [item async for item in container.query_items(
#         query=query, parameters=parameters)]
#     if not items:
#         logging.info(f"[{system_name}] 버전 {version or 'undefined'} 삭제 대상 없음")
#         return
#     start_time = time.time()
#     tasks = [delete_item(container, item["id"]) for item in items]
#     completed = sum(await asyncio.gather(*tasks))
#     elapsed = time.time() - start_time
#     logging.info(f"[{system_name}] 버전 {version or 'undefined'}: 삭제 {completed}/{len(items)}건 완료, {elapsed:.2f}s 소요")
#     work_type_code = VARIABLE.WORK_TYPE_SEED_DELETE if work_type == "seed" else VARIABLE.WORK_TYPE_SEARCH_DELETE
#     if not completed == 0:
#         history_insert(work_type_code, system_name, version or "undefined", completed)        

async def delete_all_items(container, system_name, version=None, work_type="search", batch_size=5000):
    """
    Deletes items from a Cosmos DB container in batches of 1000.
    """
    version_filter = "AND c.version = @version" if version is not None else "AND NOT IS_DEFINED(c.version)"
    query = f"SELECT TOP {batch_size} c.id FROM c WHERE c.system_name = @system_name {version_filter}"
    parameters = [{"name": "@system_name", "value": system_name}]
    if version is not None:
        parameters.append({"name": "@version", "value": version})
    total_deleted_count = 0
    total_items_to_delete = 0
    start_time = time.time()
    while True:
        items = [item async for item in container.query_items(query=query,parameters=parameters)]
        if not items:
            if total_deleted_count == 0:
                logging.info(f"[{work_type} {system_name}] 버전 {version or 'undefined'} 삭제 대상 없음")
            break
        total_items_to_delete += len(items)
        # Concurrently delete items in the current batch
        tasks = [delete_item(container, item["id"]) for item in items]
        deleted_count = sum(await asyncio.gather(*tasks))
        total_deleted_count += deleted_count
        logging.info(
            f"[{system_name}] 버전 {version or 'undefined'}: "
            f"배치 삭제 {deleted_count}/{len(items)}건 완료. "
            f"현재까지 {total_deleted_count}건 삭제."
        )
    elapsed_time = time.time() - start_time
    if total_deleted_count > 0:
        work_type_code = VARIABLE.WORK_TYPE_SEED_DELETE if work_type == "seed" else VARIABLE.WORK_TYPE_SEARCH_DELETE
        history_insert(work_type_code, system_name, version or "undefined", total_deleted_count)
    logging.info(
        f"[{work_type} {system_name}] 버전 {version or 'undefined'}: "
        f"총 {total_deleted_count}/{total_items_to_delete}건 삭제 완료, "
        f"{elapsed_time:.2f}s 소요"
    )
    return 

async def get_old_versions(container, system_name, current_version):
    query = """
        SELECT DISTINCT VALUE c.version
        FROM c
        WHERE c.system_name = @system_name
        AND (c.version < @current_version OR NOT IS_DEFINED(c.version))
    """
    parameters = [
        {"name": "@system_name", "value": system_name},
        {"name": "@current_version", "value": current_version}
    ]
    results = [v async for v in container.query_items(query=query, parameters=parameters)]
    old_versions = [v for v in results if v is not None]
    has_undefined = any(v is None for v in results)
    return old_versions, has_undefined

async def delete_old_versions_cosmos(system_name, current_version):
    try:
        async with AsyncCosmosClient(COSMOS_ENDPOINT, COSMOS_KEY) as client:
            database = client.get_database_client(DATABASE_NAME)
            container = database.get_container_client(SEARCH_CONTAINER_NAME)
            old_versions, has_undefined = await get_old_versions(container, system_name, current_version)
            if not old_versions and not has_undefined:
                logging.info(f"[SEARCH] {system_name} 삭제할 버전이 없습니다.")
                return

            logging.info(f"[SEARCH] {system_name} 삭제 대상 버전:{old_versions}")
            if old_versions:
                for version in old_versions:
                    logging.info(f"[SEARCH] {system_name} 버전 {version} 삭제 시작")
                    await delete_all_items(container, system_name, version)
            if has_undefined:
                logging.info("[SEARCH] {system_name} version 미정의 항목 삭제 시작")
                await delete_all_items(container, system_name, version=None)

    except exceptions.CosmosHttpResponseError as e:
        logging.error(f"Cosmos HTTP 에러: {e}")

    except Exception as e:
        logging.error(f"알 수 없는 에러: {e}")
        
async def delete_old_versions_cosmos_seed(system_name, version, seed_cont):
    if seed_cont == "seed":
        return
    
    async def get_keep_versions(container, system_name):
        query = """
            SELECT DISTINCT VALUE c.version
            FROM c
            WHERE IS_DEFINED(c.version) AND c.system_name = @system_name
            ORDER BY c.version DESC
        """
        parameters = [{"name": "@system_name", "value": system_name}]
        results = [v async for v in container.query_items(query=query, parameters=parameters)]
        return results[:2]  # 최신 2개 유지
    try:
        async with AsyncCosmosClient(COSMOS_ENDPOINT, COSMOS_KEY) as client:
            database = client.get_database_client(DATABASE_NAME)
            container = database.get_container_client(seed_cont)
            
            if "cpt" in system_name:
                keep_versions = await get_keep_versions(container, system_name)
                keep_last_version = keep_versions[1] if len(keep_versions) > 1 else keep_versions[0]
                version = keep_last_version
                logging.info(f"[SEED] {system_name} 유지 버전: {keep_versions}")

            old_versions, has_undefined = await get_old_versions(container, system_name, version)
            if not old_versions and not has_undefined:
                logging.info(f"[SEED] {system_name} 삭제할 버전이 없습니다.")
                return
            
            logging.info(f"[SEED] {system_name} 삭제 대상 버전:{old_versions}")
            for version in old_versions:
                logging.info(f"[SEED] 버전 {system_name} {version} 삭제 시작")
                await delete_all_items(container, system_name, version, work_type="seed")
            if has_undefined:
                logging.info(f"[SEED] {system_name} 버전 미정의 항목 삭제 시작")
                await delete_all_items(container, system_name, version=None, work_type="seed")

    except exceptions.CosmosHttpResponseError as e:
        logging.error(f"Cosmos HTTP 에러: {e}")
    except Exception as e:
        logging.error(f"알 수 없는 에러: {e}")

if __name__=="__main__":
    asyncio.run(delete_old_versions_cosmos_seed("dev-scrp","250728","scrp_seed_cont"))
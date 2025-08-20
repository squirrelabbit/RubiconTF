import os
from azure.core.credentials import AzureKeyCredential
from utils.cosmosmigration import get_all_doc_ids
import asyncio
from azure.search.documents.aio import SearchClient
import logging
import random
from utils.common import get_secret_from_key_vault
async def migration(source_index, target_index, batch_size, version):
    
    source_endpoint = os.getenv(f"AZURE_SEARCH_ENDPOINT")
    AZURE_SEARCH_SECRET_NAME = os.environ.get("AZURE_SEARCH_SECRET_NAME")
    source_api_key = get_secret_from_key_vault(AZURE_SEARCH_SECRET_NAME)
    target_endpoint = os.getenv(f"AZURE_SEARCH_ENDPOINT")
    target_api_key = get_secret_from_key_vault(AZURE_SEARCH_SECRET_NAME)

    src_credential = AzureKeyCredential(source_api_key)
    tgt_credential = AzureKeyCredential(target_api_key)

    queue = asyncio.Queue()
    async with SearchClient(endpoint=source_endpoint, index_name=source_index, credential=src_credential) as src_client, \
            SearchClient(endpoint=target_endpoint, index_name=target_index, credential=tgt_credential) as tgt_client:

        # 전체 문서 수 확인 (검색 시 include_total_count 사용)
        # initial_results = await src_client.search(
        #     search_text="*",
        #     select=["id"],
        #     top=1,
        #     order_by=["id asc"],
        #     include_total_count=True
        # )
        # total_docs = await initial_results.get_count()
        # logging.info(f"총 문서 수: {total_docs}")
        all_doc_ids = await get_all_doc_ids(src_client,version, batch_size=1000)
        logging.info(f"[index_name]{source_index}")
        logging.info(f"[index_version]{version}")
        logging.info(f"전체 ID 수: {len(all_doc_ids)}")
        if len(all_doc_ids) > 0 :
            num_producers = 1
            total_ids = len(all_doc_ids)
            partition_size = total_ids // num_producers
            partition_ranges = []
            for i in range(num_producers):
                lower_bound = all_doc_ids[i * partition_size]
                if i < num_producers - 1:
                    upper_bound = all_doc_ids[(i + 1) * partition_size]
                    partition_count = (i + 1) * partition_size - i * partition_size
                else:
                    upper_bound = None
                    partition_count = total_ids - i * partition_size
                partition_ranges.append((lower_bound, upper_bound, partition_count))
                logging.info(f"Producer {i+1} 범위: {lower_bound} ~ {upper_bound} / 할당 문서 수: {partition_count}")

            async def producer(producer_id: int, lower_bound: str, upper_bound: str, partition_count: int):
                count = 0
                current_id = None
                while count < partition_count:
                    if current_id is None:
                        cond_lower = f"id ge '{lower_bound}'"
                    else:
                        cond_lower = f"id gt '{current_id}'"
                    filter_conditions = [cond_lower]
                    if upper_bound:
                        filter_conditions.append(f"id lt '{upper_bound}'")
                    filter_str = " and ".join(filter_conditions)

                    results = await src_client.search(
                        search_text="*",
                        select=["*"],
                        filter=filter_str + f" and version eq '{version}'",
                        top=batch_size,
                        order_by=["id asc"]
                    )
                    documents = [doc async for doc in results]
                    if not documents:
                        break
                    
                    await queue.put(documents)
                    count += len(documents)
                    current_id = documents[-1]["id"]
                    logging.info(f"Producer {producer_id}: Processed {count}/{partition_count} documents")
                logging.info(f"Producer {producer_id}: Completed assigned partition.")
        # 각 프로듀서별로 lower_bound, upper_bound, partition_count 할당
            producers = []
            for i, (lower_bound, upper_bound, partition_count) in enumerate(partition_ranges):
                producers.append(asyncio.create_task(producer(i + 1, lower_bound, upper_bound, partition_count)))

                # --- Consumer 함수 ---
            async def consumer():
                while True:
                    logging.info("Consumer waiting for batch")
                    batch = await queue.get()
                    logging.info("Consumer received batch")
                    if batch is None:
                        logging.info("Consumer task done")
                        queue.task_done()
                        break
                    try:
                        # delay = random.uniform(0.5, 2.0)
                        # await asyncio.sleep(delay)
                        # upload_results = await tgt_client.merge_or_upload_documents(documents=batch)

                        # success_count = sum(r.succeeded for r in upload_results)
                        # logging.info(f"배치 업로드 완료: {success_count}/{len(batch)} 문서 성공")
                        
                        await upload(batch)
                        
                    except Exception as ex:
                        logging.info(f"업로드 중 오류: {ex}")
                    finally:
                        queue.task_done()
                        logging.info(f"배치 큐 완료")
        
            async def upload(batch, initial_delay=2):
                attempt = 0
                while True:
                    results  = await tgt_client.merge_or_upload_documents(documents=batch)
                    results_list = list(results)
                    # 성공한 문서와 실패한 문서를 분리
                    succeeded_docs = [res for res in results_list if res.succeeded]
                    failed_docs = [res for res in results_list if not res.succeeded]
                    # 모든 문서가 성공한 경우
                    if not failed_docs:
                        logging.info(f"배치 업로드 완료: {len(succeeded_docs)}/{len(batch)} 문서 성공")
                        break  # 재시도 루프 종료하고 다음 배치로 진행
                    # 일부 또는 전체 실패 시, 실패한 항목만 재시도를 위해 준비
                    logging.warning(
                        f"배치 업로드 부분 실패 (시도 {attempt + 1}): "
                        f"{len(succeeded_docs)}/{len(batch)} 성공. 실패한 항목 재시도..."
                    )
                    for res_item in failed_docs:
                        logging.error(f"  문서 업로드 실패: id={res_item.key}, error={res_item.error_message}")
                        # 실패한 문서 목록을 다음 재시도를 위해 갱신
                    succeeded_keys = {res.key for res in succeeded_docs}
                    batch = [doc for doc in batch if doc['id'] not in succeeded_keys]
                    # 재시도 전 대기 (지수 백오프 + Jitter)
                    delay = (initial_delay * (2 ** attempt)) + random.uniform(0, 1) if delay < 100 else 100
                    logging.info(f"  {delay:.2f}초 후 재시도합니다.")
                    await asyncio.sleep(delay)
                       

            num_consumers = 2
            consumers = [asyncio.create_task(consumer()) for _ in range(num_consumers)]  
            

            # 모든 프로듀서 완료 대기
            await asyncio.gather(*producers)
            # 프로듀서가 모두 완료되면 각 컨슈머에게 종료 신호(None) 전송
            for _ in range(num_consumers):
                await queue.put(None)
            await asyncio.gather(*consumers)
            logging.info("All consumers have finished")
            await queue.join()
        return
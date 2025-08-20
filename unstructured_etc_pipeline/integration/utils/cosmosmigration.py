import os
import asyncio
import logging
from dotenv import load_dotenv
from datetime import datetime
from azure.core.credentials import AzureKeyCredential
from azure.search.documents.aio import SearchClient
from azure.cosmos.aio import CosmosClient
from azure.cosmos import PartitionKey, exceptions
from tqdm.asyncio import tqdm
from utils.common import get_secret_from_key_vault

# ──────────────────────────────── 설정 로딩 ────────────────────────────────
# load_dotenv(override=True)
AZURE_SEARCH_ENDPOINT   = os.getenv("AZURE_SEARCH_ENDPOINT")
AZURE_SEARCH_SECRET_NAME = os.getenv("AZURE_SEARCH_SECRET_NAME")
AZURE_SEARCH_API_KEY    = get_secret_from_key_vault(AZURE_SEARCH_SECRET_NAME)
AZURE_SEARCH_API_VERSION = os.getenv("AZURE_SEARCH_API_VERSION")
COSMOS_ENDPOINT         = os.getenv("COSMOS_ENDPOINT")
COSMOS_DB_SECRET_NAME = os.environ.get("COSMOS_DB_SECRET_NAME")
COSMOS_KEY = get_secret_from_key_vault(COSMOS_DB_SECRET_NAME)
DATABASE_NAME           = os.getenv("DATABASE_NAME")
SEARCH_CONTAINER_NAME          = os.getenv("SEARCH_CONTAINER_NAME")

# 병렬 및 설정 파라미터
SEARCH_PAGE       = 100
MINI_BATCH        = 50
NUM_PRODUCERS     = 4
NUM_CONSUMERS     = 10
MAX_CONCURRENCY   = 32


# ──────────────────────────────── aisearchmigration.py 사용 ────────────────────────────────
async def get_all_doc_ids(client, version, batch_size: int = 1000) -> list:
    try:
        doc_ids = []
        current_id = None
        while True:
            filter_str = f"id gt '{current_id}' and version eq '{version}'" if current_id else f"version eq '{version}'"
            results = await client.search(
                search_text="*",
                select=["id"],
                filter=filter_str,
                top=batch_size,
                order_by=["id asc"]
            )
            batch_ids = [doc["id"] async for doc in results]
            if not batch_ids:
                break
            doc_ids.extend(batch_ids)
            current_id = batch_ids[-1]
            if len(batch_ids) < batch_size:
                break
    except Exception as e:
        logging.error(e)
    return doc_ids

# ──────────────────────────────── 로깅 설정 ────────────────────────────────
logging.basicConfig(level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s")

# ────────────────────── Cosmos 안전 업서트 (429 재시도) ──────────────────────
async def safe_upsert(container, doc, sem, max_attempts=10):
    async with sem:
        for attempt in range(1, max_attempts + 1):
            try:
                await container.upsert_item(doc)
                return
            except exceptions.CosmosHttpResponseError as e:
                if e.status_code == 429:
                    retry_after = e.headers.get("x-ms-retry-after-ms", "1000")
                    delay = int(retry_after) / 1000
                    await asyncio.sleep(delay)
                else:
                    logging.error(f"[{doc.get('id')}] 업서트 중 에러 발생: {e}")
                    raise
        logging.error(f"[{doc.get('id')}] 재시도 한계 초과")

# ────────────────────── 전체 ID 목록 수집 ──────────────────────
async def fetch_all_ids(client, version):
    ids = []
    last_id = None
    while True:
        filter_str = f"version eq '{version}'"
        if last_id:
            filter_str += f" and id gt '{last_id}'"
        resp = await client.search(
            search_text="*",
            select=["id"],
            filter=filter_str,
            order_by=["id asc"],
            top=SEARCH_PAGE
        )
        batch = [d["id"] async for d in resp]
        if not batch:
            break
        ids.extend(batch)
        last_id = batch[-1]
    return ids

# ────────────────────── Producer 함수 ──────────────────────
async def producer(pid, lower_bound, upper_bound, version, queue, s_client):
    current_id = None
    first = True
    while True:
        conds = [f"version eq '{version}'"]
        if current_id:
            conds.append(f"id gt '{current_id}'" if not first else f"id ge '{current_id}'")
        elif lower_bound:
            conds.append(f"id ge '{lower_bound}'")
        if upper_bound:
            conds.append(f"id lt '{upper_bound}'")
        filter_str = " and ".join(conds)
        results = await s_client.search(
            "*",
            filter=filter_str,
            order_by=["id asc"],
            top=SEARCH_PAGE
        )
        docs = [dict(d) async for d in results]
        if not docs:
            break
        await queue.put(docs)
        current_id = docs[-1]["id"]
        first = False
    logging.info(f"[Producer-{pid}] 완료")

# ────────────────────── Consumer 함수 ──────────────────────
async def consumer(cid, queue, container, sem, pbar, failed_docs):
    while True:
        docs = await queue.get()
        if docs is None:
            queue.task_done()
            break
        for i in range(0, len(docs), MINI_BATCH):
            batch = docs[i:i+MINI_BATCH]
            results = await asyncio.gather(*[
                safe_upsert(container, doc, sem)
                for doc in batch
            ], return_exceptions=True)
            for doc, result in zip(batch, results):
                if isinstance(result, Exception):
                    failed_docs.append(doc)
            pbar.update(len(batch))
        queue.task_done()

# ────────────────────── 재업로드 함수 ──────────────────────
async def retry_failed_uploads(container, failed_docs):
    if not failed_docs:
        logging.info("모든 문서가 성공적으로 업로드됨")
        return
    logging.warning(f"재시도 대상 문서 수: {len(failed_docs)}")
    sem = asyncio.Semaphore(MAX_CONCURRENCY)
    for doc in failed_docs:
        try:
            await safe_upsert(container, doc, sem)
        except Exception as e:
            logging.error(f"[{doc.get('id')}] 재업로드 실패: {e}")

# ────────────────────── 메인 함수 ──────────────────────
async def transfer_data(index_name: str, version: str):
    queue = asyncio.Queue(maxsize=NUM_PRODUCERS * 2)
    sem = asyncio.Semaphore(MAX_CONCURRENCY)
    failed_docs = []
    async with SearchClient(
        endpoint=AZURE_SEARCH_ENDPOINT,
        index_name=index_name,
        credential=AzureKeyCredential(AZURE_SEARCH_API_KEY),
        api_version=AZURE_SEARCH_API_VERSION
    ) as s_client, CosmosClient(
        COSMOS_ENDPOINT, COSMOS_KEY
    ) as cosmos_client:
        db = await cosmos_client.create_database_if_not_exists(id=DATABASE_NAME)
        container = await db.create_container_if_not_exists(
            id=SEARCH_CONTAINER_NAME,
            partition_key=PartitionKey(path="/id")
        )
        # 전체 ID 수집
        ids = await fetch_all_ids(s_client, version)
        total = len(ids)
        logging.info(f"마이그레이션 대상 문서 수: {total:,}")
        if total == 0:
            return
        chunk = (total + NUM_PRODUCERS - 1) // NUM_PRODUCERS
        bounds = [ids[i * chunk] if i * chunk < total else None for i in range(NUM_PRODUCERS + 1)]
        # 진행률 바
        pbar = tqdm(total=total, desc="Migrating", unit="docs", mininterval=0.2)
        producers = [
            asyncio.create_task(producer(i+1, bounds[i], bounds[i+1], version, queue, s_client))
            for i in range(NUM_PRODUCERS)
        ]
        consumers = [
            asyncio.create_task(consumer(j+1, queue, container, sem, pbar, failed_docs))
            for j in range(NUM_CONSUMERS)
        ]
        await asyncio.gather(*producers)
        for _ in range(NUM_CONSUMERS):
            await queue.put(None)
        await asyncio.gather(*consumers)
        pbar.close()
        await retry_failed_uploads(container, failed_docs)
        logging.info("마이그레이션 완료")
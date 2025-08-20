import os
import asyncpg
from media.modules.pim_media_data import unique_urls_all
from media.proc_media_common import MediaSearchContainer, MediaRefData, MediaSearch
from media.common_utils import generate_id
from datetime import datetime,timezone
from utils.data_postgres import DBManager
from urllib.parse import quote
from utils.common import get_secret_from_key_vault
import asyncio
from utils.log_manager import LogManager
from tqdm.asyncio import tqdm_asyncio

PGDB_USERNAME = os.environ.get("PGDB_USERNAME")
PGDB_SECRET_NAME = os.getenv("PGDB_SECRET_NAME")
PG_PWD_KEY =quote(get_secret_from_key_vault(PGDB_SECRET_NAME))
PGDB_HOST = os.environ.get("PGDB_HOST")
PGDB_DBNAME = os.environ.get("PGDB_DBNAME")
PGDB_PORT = os.environ.get("PGDB_PORT")

SYSTEM_NAME = os.environ['SYSTEM_NAME']
PGDB_TABLE_NAME = os.environ.get("PGDB_TABLE_NAME")
IMAGE_TABLE_NAME = os.environ['IMAGE_TABLE_NAME']

def safe_strip(val):
    return val.strip() if isinstance(val, str) else ""

async def media_main(version):
    ref_data_list = []
    loaded_list = []
    last_version, current_version = version
    global alpha_shared_pool, cloocus_shared_pool
    alpha_shared_pool = await asyncpg.create_pool(
        f"postgresql://{PGDB_USERNAME}:{PG_PWD_KEY}@{PGDB_HOST}:{PGDB_PORT}/{PGDB_DBNAME}",
        min_size=5, max_size=50, timeout=30
    )
    cloocus_shared_pool = await asyncpg.create_pool(
        f"postgresql://{PGDB_USERNAME}:{PG_PWD_KEY}@{PGDB_HOST}:{PGDB_PORT}/cloocusdb",
        min_size=5, max_size=50, timeout=30
    )
    await LogManager.info("media_main 시작")
    # 먼저 PGDB의 테이블 a를 조회
    async with DBManager(db_name=PGDB_DBNAME, pool=alpha_shared_pool) as db1:
        records_a = await db1.fetch(f"SELECT * FROM {PGDB_TABLE_NAME}")
        a_dict = {r['model_code']: r for r in records_a}
    # 다음 IMAGE_TABLE 조회
    async with DBManager(db_name='cloocusdb', pool=cloocus_shared_pool) as db2:
        records_b = await db2.fetch(f"SELECT * FROM {IMAGE_TABLE_NAME} WHERE upload_version = '{current_version}';")
    # Python에서 조인
    results = []
    for b in records_b:
        model_code = b['pim_id'].split('_')[0].strip()
        a = a_dict.get(model_code)
        if a:
            # logger.info(a)
            merged = {**a, **b}
            results.append(merged)
    unique_urls = await unique_urls_all(results)
    semaphore = asyncio.Semaphore(20)  # 동시에 최대 20개만 처리
    async def process_row_limited(row):
        async with semaphore:
            return await process_row(row)

    async def process_row(row):
        url_key = row['origin_img_url'] or row['origin_mp4_url']
        if url_key not in unique_urls:
            return None, None
        media_item = unique_urls[url_key]
        row['image_description'] = media_item.image_description
        row['id'] = f"{row['pim_id']}_cate" if row.get('category1') else row['pim_id']
        image_data = row['img_url'] or row['mp4_url'] or ''
        image_type = row['image_type']
        chunk_data = row['image_description']
        semantic_chunk_data = "" if row.get('features') is None else row.get('features')
        
        async with MediaSearchContainer() as cosmos:
            container = await cosmos.get_container()
            query = """
            SELECT * FROM c
            WHERE c.system_name = @system_name
            AND c.version = @version
            AND ARRAY_CONTAINS(c.model_code, @model_code)
            AND c.chunk = @chunk
            AND c.semantic_chunk = @semantic_chunk
            AND c.type = @type
            AND c.display_seq = @display_seq
            AND c.chunk_seq = @chunk_seq
            AND ARRAY_CONTAINS(c.img_data, @img_data)
            """
            params = [
                {"name": "@system_name", "value": SYSTEM_NAME},
                {"name": "@version", "value": last_version},
                {"name": "@model_code", "value": row.get("model_code")},
                {"name": "@chunk", "value": chunk_data},
                {"name": "@type", "value": safe_strip(image_type)},
                {"name": "@semantic_chunk", "value": semantic_chunk_data},
                {"name": "@display_seq", "value": row.get("display_seq")},
                {"name": "@chunk_seq", "value": row.get("chunk_seq")},
                {"name": "@img_data", "value": safe_strip(image_data)},
            ]
            existing_docs = [doc async for doc in container.query_items(query=query, parameters=params)]
        
        if existing_docs:
            for item in existing_docs:
                index = MediaSearch(**item)
                index.version = current_version
                index = generate_id(index)
                return None, index
        else:
            index_obj = MediaRefData(
                title=safe_strip(row.get('title')),
                blob_path=safe_strip(row.get('blob_path')),
                chunk=chunk_data,
                chunk_seq=int(row.get('display_seq', 0) or 0),
                semantic_chunk=semantic_chunk_data,
                category1=safe_strip(row.get('category1')) if row.get('category1') else '',
                category2=safe_strip(row.get('category2')) if row.get('category2') else '',
                category3=safe_strip(row.get('category3')) if row.get('category3') else '',
                model_code=[] if not row.get('model_code') else [safe_strip(row.get('model_code'))],
                is_display=int(row.get('is_valid', 0) or 0),
                display_seq=int(row.get('pim_id').split('_')[1].strip() or 0),
                goods_id=[safe_strip(row.get('goods_id'))],
                goods_nm=[safe_strip(row.get('goods_nm'))],
                img_data=[safe_strip(image_data)],
                type=safe_strip(image_type),
                reg_date=row.get('sys_reg_dtm').astimezone(timezone.utc).isoformat() if row.get('sys_reg_dtm') else None,
                disp_strt_dtm=row.get('disp_strt_dtm'),
                disp_end_dtm=row.get('disp_end_dtm'),
                model_name=[safe_strip(row.get('model_name'))],
            )
            return index_obj, None
    
    tasks = [process_row_limited(row) for row in results]
    processed = []
    for coro in tqdm_asyncio.as_completed(tasks, desc="Processing rows", total=len(tasks)):
        result = await coro
        processed.append(result)
    # 나눠 담기
    for ref, loaded in processed:
        if ref:
            ref_data_list.append(ref)
        if loaded:
            loaded_list.append(loaded)
    print(len(results))
    print(len(ref_data_list))
    print(len(loaded_list))
    return ref_data_list, loaded_list




if __name__ =="__main__":
    ref, load = asyncio.run(media_main(("250706","2507280147")))
    
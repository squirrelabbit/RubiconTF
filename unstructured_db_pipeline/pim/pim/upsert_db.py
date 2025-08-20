import asyncio
import json
from pim.common_utils import generate_pim_db_id
import asyncpg
from azure.core.credentials import AzureKeyCredential
from azure.search.documents.aio import SearchClient
import os
from utils.common import get_secret_from_key_vault
# ─── 설정 ───

AZURE_SEARCH_ENDPOINT = os.environ.get("AZURE_SEARCH_ENDPOINT")
AZURE_SEARCH_SECRET_NAME = os.environ.get("AZURE_SEARCH_SECRET_NAME")
AZURE_SEARCH_KEY = get_secret_from_key_vault(AZURE_SEARCH_SECRET_NAME)
AZURE_SEARCH_API_VERSION = os.environ.get("AZURE_SEARCH_API_VERSION")
INDEX_NAME = os.environ['SYSTEM_NAME']
PAGE_SIZE             = 1000

PGDB_USERNAME = os.environ.get("PGDB_USERNAME")
PGDB_SECRET_NAME = os.getenv("PGDB_SECRET_NAME")
PGDB_PASSWORD =get_secret_from_key_vault(PGDB_SECRET_NAME)
PGDB_HOST = os.environ.get("PGDB_HOST")

# PGDB_DBNAME   = "cloocusdb"
PGDB_DBNAME = "alpha"
TABLE_NAME    = "pim_index_data"  # 기존 테이블에 덮어씌우려면 truncate, 아니면 새 테이블명 지정

# 가져올 필드들
SELECT_FIELDS = [
    "id","original_id","bu","category1","category2","category3","title","blob_path",
    "chunk","semantic_chunk","semantic_title",
    "filter_id","display_seq","chunk_seq","semantic_chunk_seq",
    "family_code","family_name","common_code","goods_id","goods_nm",
    "img_data","model_group_code","model_code","model_name","product_model"
]

def to_jsonb(value):
    if value is None:
        return None
    if isinstance(value, (list, dict)):
        return json.dumps(value)
    return value

def select_desired_fields(doc):
    return {
        "id":               doc["id"],
        "original_id":      doc["original_id"],
        "bu":               doc.get("bu"),
        "category1":        doc.get("category1"),
        "category2":        doc.get("category2"),
        "category3":        doc.get("category3"),
        "title":            doc.get("title"),
        "blob_path":        doc.get("blob_path"),
        "chunk":            doc.get("chunk"),
        "semantic_chunk":   doc.get("semantic_chunk"),
        "semantic_title":   doc.get("semantic_title"),
        "filter_id":        doc.get("filter_id"),
        "display_seq":      doc.get("display_seq"),
        "chunk_seq":        doc.get("chunk_seq"),
        "semantic_chunk_seq":doc.get("semantic_chunk_seq"),
        "family_code":      to_jsonb(doc.get("family_code")),
        "family_name":      to_jsonb(doc.get("family_name")),
        "common_code":      to_jsonb(doc.get("common_code")),
        "goods_id":         to_jsonb(doc.get("goods_id")),
        "goods_nm":         json.loads(to_jsonb(doc.get("goods_nm")))[0].replace('\\"', '"'),
        "img_data":         to_jsonb(doc.get("img_data")),
        "model_group_code": to_jsonb(doc.get("model_group_code")),
        "model_code":       to_jsonb(doc.get("model_code")),
        "model_name":       to_jsonb(doc.get("model_name")),
        "product_model":    to_jsonb(doc.get("product_model")),
    }


# util: 리스트를 batch_size만큼씩 자르는 제너레이터
def chunked(iterable, batch_size):
    for i in range(0, len(iterable), batch_size):
        yield iterable[i : i + batch_size]
        

async def fetch_all_chunks(version):
    client = SearchClient(
        endpoint=AZURE_SEARCH_ENDPOINT,
        index_name=INDEX_NAME,
        credential=AzureKeyCredential(AZURE_SEARCH_KEY)
    )
    all_docs = []
    last_id = None
    async with client:
        while True:
            results = await client.search(
                search_text="*",
                select=SELECT_FIELDS,
                order_by=["id asc"],
                filter=f"id gt '{last_id}' and version eq '{version}'" if last_id else f"version eq '{version}'",
                top=PAGE_SIZE,
                include_total_count=(last_id is None)
            )
            batch = [ r async for r in results ]
            if not batch:
                break

            all_docs.extend(batch)
            last_id = batch[-1]["id"]
            print(f"... {len(all_docs)} 건 가져옴 (last_id={last_id})")

    return all_docs

async def insert_data_to_postgres(records):
    conn = await asyncpg.connect(
        user=PGDB_USERNAME,
        password=PGDB_PASSWORD,
        host=PGDB_HOST,
        database=PGDB_DBNAME
    )
    try:
        # # 1) 테이블 생성 보장
        # await conn.execute(f"""
        #     CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
        #         id TEXT PRIMARY KEY,
        #         bu TEXT, category1 TEXT, category2 TEXT, category3 TEXT,
        #         title TEXT, blob_path TEXT,
        #         chunk TEXT, semantic_chunk TEXT, semantic_title TEXT,
        #         semantic_question TEXT, semantic_keyword TEXT,
        #         filter_id TEXT, display_seq INTEGER, chunk_seq INTEGER,
        #         semantic_chunk_seq INTEGER,
        #         family_code JSONB, family_name JSONB, common_code JSONB,
        #         goods_id JSONB, goods_nm JSONB,
        #         img_data JSONB, model_group_code JSONB,
        #         model_code JSONB, model_name JSONB, product_model JSONB
        #     );
        # """)

        # # 2) 기존 데이터를 모두 지우고 시퀀스 리셋
        # status = await conn.execute(f"TRUNCATE TABLE {TABLE_NAME} RESTART IDENTITY;")
        # print(f"{TABLE_NAME} {status} 완료.")

        # 3) 배치 upsert 
        insert_sql = f"""
        INSERT INTO {TABLE_NAME}(
            id, bu, category1, category2, category3, title, blob_path,
            chunk, semantic_chunk, semantic_title,
            filter_id, display_seq, chunk_seq,
            semantic_chunk_seq, family_code, family_name, common_code,
            goods_id, goods_nm, img_data, model_group_code, model_code,
            model_name, product_model, updated_on
        ) VALUES (
            $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23,$24, (now() at time zone 'Asia/Seoul')
        )
        ON CONFLICT(id) DO NOTHING
        """
        

        # 4) executemany 
        values = [
            (
                generate_pim_db_id(model_code=rec["model_code"], chunk=rec["chunk"], semantic_chunk=rec["semantic_chunk"]), 
                rec["bu"], rec["category1"], rec["category2"], rec["category3"],
                rec["title"], rec["blob_path"], rec["chunk"], rec["semantic_chunk"],
                rec["semantic_title"],
                rec["filter_id"], rec["display_seq"], rec["chunk_seq"],
                rec["semantic_chunk_seq"], rec["family_code"], rec["family_name"],
                rec["common_code"], rec["goods_id"], rec["goods_nm"], rec["img_data"],
                rec["model_group_code"], rec["model_code"], rec["model_name"],
                rec["product_model"]
            )
            for rec in records
        ]
        
        # # 전체 Insert 방식 
        # await conn.executemany(insert_sql, values)
        # # print(f"총 {len(records)} 건 데이터 적재 완료.")
        # print(f"{len(values)}건 batch upsert 완료.")
        
        # batch insert 방식 
        BATCH_SIZE = 1000  # 한 번에 1,000건씩
        total = 0
        
        for batch in chunked(values, BATCH_SIZE):
            await conn.executemany(insert_sql, batch)
            total += len(batch)
            print(f"  → {len(batch)}건 upsert 완료 (누적 {total}건)")

        print(f"전체 {total}건 upsert 완료.")
        
    finally:
        await conn.close()

import re
async def main(version):
    # 1) Azure Search 에서 전체 문서 추출
    raw_docs = await fetch_all_chunks(version)
    print(f"최종 가져온 문서 수: {len(raw_docs)}")
    
    pattern = re.compile(r'^[^a-zA-Z0-9가-힣]+$')
    # 선택 후 필터링
    selected = [
        select_desired_fields(d)
        for d in raw_docs
        if not pattern.match(d.get("semantic_chunk") or "")
    ]

    # 3) PostgreSQL에 배치 upsert
    await insert_data_to_postgres(selected)

if __name__ == "__main__":
    asyncio.run(main("250717"))
import asyncio
import json
from pim.common_utils import generate_pim_db_id
import asyncpg
import os
from utils.common import get_secret_from_key_vault
import re
# ─── 설정 ───
PGDB_USERNAME = os.environ.get("PGDB_USERNAME")
PGDB_SECRET_NAME = os.getenv("PGDB_SECRET_NAME")
PGDB_PASSWORD = get_secret_from_key_vault(PGDB_SECRET_NAME)
PGDB_HOST = os.environ.get("PGDB_HOST")
PGDB_DBNAME = "cloocusdb"
TABLE_NAME = "pim_index_data_test"

# 정규식 precompile
INVALID_PATTERN = re.compile(r'^[^a-zA-Z0-9가-힣]+$')

def to_jsonb(value):
    if value is None:
        return None
    if isinstance(value, (list, dict)):
        return json.dumps(value)
    return value

from datetime import datetime
def record_to_dict(rec):
    return {
        "id": rec["id"],
        "bu": rec.get("bu"),
        "category1": rec.get("category1"),
        "category2": rec.get("category2"),
        "category3": rec.get("category3"),
        "title": rec.get("title"),
        "blob_path": rec.get("blob_path"),
        "chunk": rec.get("chunk"),
        "semantic_chunk": rec.get("semantic_chunk"),
        "semantic_title": rec.get("semantic_title"),
        "filter_id": rec.get("filter_id"),
        "display_seq": rec.get("display_seq"),
        "chunk_seq": rec.get("chunk_seq"),
        "semantic_chunk_seq": rec.get("semantic_chunk_seq"),
        "family_code": to_jsonb(rec.get("family_code")),
        "family_name": to_jsonb(rec.get("family_name")),
        "common_code": to_jsonb(rec.get("common_code")),
        "goods_id": to_jsonb(rec.get("goods_id")),
        "goods_nm": to_jsonb(rec.get("goods_nm")),
        "img_data": to_jsonb(rec.get("img_data")),
        "model_group_code": to_jsonb(rec.get("model_group_code")),
        "model_code": to_jsonb(rec.get("model_code")),
        "model_name": to_jsonb(rec.get("model_name")),
        "product_model": to_jsonb(rec.get("product_model")),
        "updated_on" : rec.get("updated_on")
    }
    
def chunked(iterable, batch_size):
    for i in range(0, len(iterable), batch_size):
        yield iterable[i : i + batch_size]
        
async def fetch_chunks_from_postgres(version):
    conn = await asyncpg.connect(
        user=PGDB_USERNAME,
        password=PGDB_PASSWORD,
        host=PGDB_HOST,
        database="alpha"
    )
    try:
        query = f"""
        SELECT * FROM pim_index_data
        WHERE updated_on::date = '{version}'
        ORDER BY id ASC
        """
        records = await conn.fetch(query)
        print(f"총 {len(records)}건 SELECT 완료")
        return records
    finally:
        await conn.close()
        
async def insert_data_to_postgres(records):
    conn = await asyncpg.connect(
        user=PGDB_USERNAME,
        password=PGDB_PASSWORD,
        host=PGDB_HOST,
        database=PGDB_DBNAME
    )
    try:
        insert_sql = f"""
        INSERT INTO {TABLE_NAME}(
            id, bu, category1, category2, category3, title, blob_path,
            chunk, semantic_chunk, semantic_title,
            filter_id, display_seq, chunk_seq,
            semantic_chunk_seq, family_code, family_name, common_code,
            goods_id, goods_nm, img_data, model_group_code, model_code,
            model_name, product_model, updated_on
        ) VALUES (
            $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,
            $11,$12,$13,$14,$15,$16,$17,$18,$19,$20,
            $21,$22,$23,$24, $25
        )
        ON CONFLICT(id) DO NOTHING
        """
        values = [
            (
                generate_pim_db_id(
                    model_code=rec["model_code"],
                    chunk=rec["chunk"],
                    semantic_chunk=rec["semantic_chunk"]
                ),
                # rec["id"],
                rec["bu"], rec["category1"], rec["category2"], rec["category3"],
                rec["title"], rec["blob_path"], rec["chunk"], rec["semantic_chunk"],
                rec["semantic_title"], rec["filter_id"], rec["display_seq"], rec["chunk_seq"],
                rec["semantic_chunk_seq"], rec["family_code"], rec["family_name"],
                rec["common_code"], rec["goods_id"], rec["goods_nm"], rec["img_data"],
                rec["model_group_code"], rec["model_code"], rec["model_name"],
                rec["product_model"], 
                rec["updated_on"] if rec["updated_on"] else datetime.fromisoformat("2025-07-09T15:00:00")
            )
            for rec in records
        ]
        BATCH_SIZE = 1000
        total = 0
        for batch in chunked(values, BATCH_SIZE):
            await conn.executemany(insert_sql, batch)
            total += len(batch)
            print(f"  → {len(batch)}건 upsert 완료 (누적 {total}건)")
        print(f"전체 {total}건 upsert 완료.")
    finally:
        await conn.close()
        
async def main(version):
    # 1) PostgreSQL에서 데이터 가져오기
    raw_records = await fetch_chunks_from_postgres(version)
    # 2) dict 변환
    selected = []
    for r in raw_records:
        rec = record_to_dict(r)
        # Python에서도 재확인
        if INVALID_PATTERN.match(rec["semantic_chunk"]):
            continue
        selected.append(rec)
    print(f"최종 유효 데이터 수: {len(selected)}")
    # 3) PostgreSQL에 insert
    await insert_data_to_postgres(selected)
    
if __name__ == "__main__":
    asyncio.run(main("250714"))
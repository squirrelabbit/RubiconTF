import asyncio
from utils.data_postgres import DBManager
from tqdm.asyncio import tqdm
from media.modules.proc_embedding import search_vector,search_vector_for_url
from media.modules.pim_media_data import unique_urls_media_type
import asyncpg
import os 
from urllib.parse import quote
from utils.common import get_secret_from_key_vault

PGDB_USERNAME = os.environ.get("PGDB_USERNAME")
PGDB_SECRET_NAME = os.getenv("PGDB_SECRET_NAME")
PGDB_PASSWORD =quote(get_secret_from_key_vault(PGDB_SECRET_NAME))
PGDB_HOST = os.environ.get("PGDB_HOST")
PGDB_DBNAME = os.environ.get("PGDB_DBNAME")
PGDB_PORT = os.environ.get("PGDB_PORT")
PGDB_TABLE_NAME = os.environ.get("PGDB_TABLE_NAME")

IMAGE_TABLE_NAME = os.environ.get("IMAGE_TABLE_NAME")
IMAGE_LIST_PROC_TABLE_NAME = os.environ.get("IMAGE_LIST_PROC_TABLE_NAME")

def get_last_update(image_urls,media_type):
    result_data = None
    for img_url in image_urls:
        for m in media_data:
            if img_url == m.image_url and m.image_type == media_type:
                if result_data is None or m.modification_date > result_data.modification_date:
                    result_data = m

    return result_data

async def insert_db(image_urls,target_url,media_type, max_retries: int = 3):
    for attempt in range(1, max_retries + 1):
        try:
            async with DBManager(db_name='cloocusdb',pool=shared_pool) as db:
                for image_data in image_urls:
                    await db.execute(f"""
                        INSERT INTO {IMAGE_LIST_PROC_TABLE_NAME}(media_type,meta_url, source_url, target_url,score)
                        VALUES($1,$2,$3,$4,$5)
                    """,media_type,image_data['meta_url'], image_data['image_url'], target_url,image_data['score'])
                
        except Exception as e:
            print(f":경고: Azure Search upload attempt {attempt} failed: {e}")
            if attempt == max_retries:
                raise
            await asyncio.sleep(1 * attempt)


async def run_proc(semaphore, image_url,media_type):
    async with semaphore:
        async with DBManager(db_name='cloocusdb',pool=shared_pool) as db:
            check_data = await db.fetch_json(f"SELECT * FROM {IMAGE_LIST_PROC_TABLE_NAME} WHERE meta_url = $1",image_url)

        if len(check_data) > 0 :
            return

        image_urls = []

        async def expand_similar_urls(seed_url):
            vector = await search_vector_for_url(seed_url)
            if not vector:
                return

            results = await search_vector(image_vector=vector,media_type=media_type,threshold=0.97)
            for doc in results:
                url = doc.get('image_url')
                image_urls.append({ "meta_url": image_url, "image_url": url, "score": doc.get('@search.score')})

        # 시작 URL로부터 확장
        await expand_similar_urls(image_url)

        target_url = None

        if media_type == "mp4":
            last_data = get_last_update(image_urls=[image['image_url'] for image in image_urls],media_type="mp4")
        else:
            last_data = get_last_update(image_urls=[image['image_url'] for image in image_urls],media_type="image")

        if last_data:
            target_url = last_data.image_url
        else:
            return

        

        await insert_db(image_urls=image_urls,target_url=target_url,media_type=media_type)



# 여러 이미지 URL 처리
async def process_all_images():
    global media_data
    query = f"""
            SELECT origin_img_url,origin_mp4_url FROM {IMAGE_TABLE_NAME} 
            """
    
    async with DBManager(db_name='cloocusdb',pool=shared_pool) as db:
        records = await db.fetch(query)
        db_results = [dict(record) for record in records]

    query = f"""SELECT * FROM {PGDB_TABLE_NAME};"""
    
    async with DBManager(db_name=PGDB_DBNAME) as db:
        records = await db.fetch(query)
        pim_results = [dict(record) for record in records]
        
    uq_img = await unique_urls_media_type(pim_results,'image')
    uq_mp4 = await unique_urls_media_type(pim_results,'mp4')
    media_data = []

    db_ids = {item['origin_img_url'] for item in db_results}
    media_data.extend([item for item in uq_img if item.image_url not in db_ids])

    db_ids = {item['origin_mp4_url'] for item in db_results}
    media_data.extend([item for item in uq_mp4 if item.image_url not in db_ids])

    tasks = []
    semaphore = asyncio.Semaphore(100)
    
    for r in media_data:
        tasks.append(run_proc(semaphore=semaphore,image_url=r.image_url,media_type=r.image_type))

    await tqdm.gather(*tasks)

async def get_unique_source_url():    
    query = f"""
        SELECT DISTINCT source_url,media_type
        FROM {IMAGE_LIST_PROC_TABLE_NAME}
        WHERE source_url IN (
            SELECT source_url
            FROM {IMAGE_LIST_PROC_TABLE_NAME}
            GROUP BY source_url
            HAVING COUNT(DISTINCT target_url) > 1
        );
    """
    async with DBManager(db_name='cloocusdb',pool=shared_pool) as db:
        records = await db.fetch(query)
    return [dict(record) for record in records]

async def get_target_url(source_url):    
    query = f"""
        SELECT target_url FROM {IMAGE_LIST_PROC_TABLE_NAME} WHERE source_url = $1;
    """
    async with DBManager(db_name='cloocusdb',pool=shared_pool) as db:
        records = await db.fetch(query,source_url)
    return [dict(record) for record in records]

async def update_target_url(old_target,new_target):
    query = f"""
        UPDATE {IMAGE_LIST_PROC_TABLE_NAME} SET target_url = $1 WHERE target_url = $2;
    """
    async with DBManager(db_name='cloocusdb',pool=shared_pool) as db:
        await db.fetch(query,new_target,old_target)


async def last_update_target_url(semaphore,source_url,media_type):
    async with semaphore:
        target_urls = await get_target_url(source_url)

        new_target = None

        if media_type == "mp4":
            last_data = get_last_update(image_urls=[image['target_url'] for image in target_urls],media_type="mp4")
        else:
            last_data = get_last_update(image_urls=[image['target_url'] for image in target_urls],media_type="image")

        new_target = last_data.image_url

       
        for t in target_urls:
            target_url = t['target_url']
            if target_url != new_target:
                await update_target_url(target_url,new_target)

async def dup_process():
    source_urls = await get_unique_source_url()

    tasks = []
    semaphore = asyncio.Semaphore(20)

    for r in source_urls:
        tasks.append(last_update_target_url(semaphore,r['source_url'],r['media_type']))

    await tqdm.gather(*tasks)

async def process_media_duplicate():
    global shared_pool
    shared_pool = await asyncpg.create_pool(
        f"postgresql://{PGDB_USERNAME}:{PGDB_PASSWORD}@{PGDB_HOST}:{PGDB_PORT}/cloocusdb",
        min_size=5,
        max_size=50,
        timeout=30
    )

    await process_all_images()
    await dup_process()


import asyncio
if __name__=="__main__":
    asyncio.run(process_media_duplicate())
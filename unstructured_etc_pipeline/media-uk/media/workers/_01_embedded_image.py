import aiohttp
import asyncio
from utils.data_postgres import DBManager
import os
from utils.common import get_secret_from_key_vault
from azure.search.documents.aio import SearchClient
from azure.core.credentials import AzureKeyCredential
from media.modules.pim_media_data import text_to_base64
from tqdm.asyncio import tqdm
from media.modules.proc_embedding import mp4_to_gif
from utils.data_blob import AzureBlobStorageAsync
from media.modules.pim_media_data import unique_urls_all

# Vision API 설정
VISION_ENDPOINT = os.environ.get("VISION_ENDPOINT")
# VISION_SUBSCRIPTION_KEY = os.environ.get("VISION_SUBSCRIPTION_KEY")
VISION_SECRET_NAME = os.environ.get("VISION_SECRET_NAME")
VISION_SUBSCRIPTION_KEY = get_secret_from_key_vault(VISION_SECRET_NAME)
VISION_API_URL = f"{VISION_ENDPOINT}{os.environ.get('VISION_API_PATH')}"

AZURE_SEARCH_ENDPOINT = os.environ.get("AZURE_SEARCH_ENDPOINT")
AZURE_SEARCH_SECRET_NAME = os.environ.get("AZURE_SEARCH_SECRET_NAME")
AZURE_SEARCH_API_KEY = get_secret_from_key_vault(AZURE_SEARCH_SECRET_NAME)
# AZURE_SEARCH_API_KEY = os.environ.get("AZURE_SEARCH_API_KEY")
AZURE_SEARCH_API_VERSION = os.environ.get("AZURE_SEARCH_API_VERSION")
IMAGE_CHECK_INDEX_NAME = os.environ.get("IMAGE_CHECK_INDEX_NAME")

PGDB_DBNAME = os.environ.get("PGDB_DBNAME")
PGDB_TABLE_NAME = os.environ.get("PGDB_TABLE_NAME")


async def upload_to_azure_search(documents, max_retries: int = 3):
    for attempt in range(1, max_retries + 1):
        try:
            async with SearchClient(
                endpoint=AZURE_SEARCH_ENDPOINT,
                index_name=IMAGE_CHECK_INDEX_NAME,
                credential=AzureKeyCredential(AZURE_SEARCH_API_KEY)
            ) as client:
                result = await client.upload_documents(documents)
                errors = [r for r in result if not r.succeeded]
                return
        except Exception as e:
            print(f":경고: Azure Search upload attempt {attempt} failed: {e}")
            if attempt == max_retries:
                raise
            await asyncio.sleep(1 * attempt)

async def check_search(documents, max_retries: int = 3):
    for attempt in range(1, max_retries + 1):
        try:
            async with SearchClient(
                endpoint=AZURE_SEARCH_ENDPOINT,
                index_name=IMAGE_CHECK_INDEX_NAME,
                credential=AzureKeyCredential(AZURE_SEARCH_API_KEY)
            ) as client:
                results = await client.search(filter=f"image_url eq '{documents['image_url']}'")
                result = [doc async for doc in results]
                if result and len(result) > 0 :
                    return True
                else:
                    return False
        except Exception as e:
            print(f":경고: Azure Search upload attempt {attempt} failed: {e}")
            if attempt == max_retries:
                raise
            await asyncio.sleep(1 * attempt)

        
async def get_embedding_async(semaphore,image_url,media_type,az_blob, max_retries=5):
    async with semaphore:
        if await check_search({"image_url": image_url}):
            return 
        if media_type == "mp4":
            gif_url = await mp4_to_gif(image_url,az_blob,text_to_base64(image_url))
            if not gif_url:
                return
        headers = {
            "Ocp-Apim-Subscription-Key": VISION_SUBSCRIPTION_KEY
        }
        data = {
            'url': gif_url if media_type == "mp4" else image_url
        }

        for attempt in range(1, max_retries + 1):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(VISION_API_URL, headers=headers, json=data) as response:
                        if response.status == 200:
                            json_data = await response.json()
                            doc = {
                                "id": text_to_base64(image_url),
                                "media_type": media_type,
                                "image_url": image_url,
                                "imageVector": json_data["vector"]
                            }                        
                            await upload_to_azure_search([doc])
                            return
                        elif response.status == 429:
                            wait_time = attempt * 2
                            print(f":hourglass: 429 too many requests. Retrying in {wait_time}s for {image_url}")
                            await asyncio.sleep(wait_time)
                        else:
                            error_text = await response.text()
                            print(f":x: 임베딩 실패: {response.status} {error_text} : {image_url}")

                            doc = {
                                "id": text_to_base64(image_url),
                                "media_type": media_type,
                                "image_url": image_url,
                                "imageVector": []
                            }                        
                            await upload_to_azure_search([doc])
                            return
            except Exception as e:
                wait_time = attempt * 2
                print(f"raise error Retrying in {wait_time}s for {image_url}")
                await asyncio.sleep(wait_time)



# 여러 이미지 URL 처리
async def process_image_embedding():
    query =f"""SELECT * FROM {PGDB_TABLE_NAME};"""
    
    async with DBManager(db_name=PGDB_DBNAME) as db:
        records = await db.fetch(query)
        results = [dict(record) for record in records]

    media_urls = await unique_urls_all(results)
        
    tasks = []
    semaphore = asyncio.Semaphore(20)
    az_blob = AzureBlobStorageAsync()
    
    for r in [value for key,value in media_urls.items()]:
        tasks.append(get_embedding_async(semaphore,r.image_url,r.image_type,az_blob))
    
    await tqdm.gather(*tasks)

import asyncio
if __name__=="__main__":
    asyncio.run(process_image_embedding())
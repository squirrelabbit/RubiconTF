import aiohttp
import asyncio
from utils.data_postgres import DBManager
import os
from utils.common import get_secret_from_key_vault
from azure.search.documents.aio import SearchClient
from azure.search.documents.models import VectorizedQuery
from azure.core.credentials import AzureKeyCredential
from media.modules.pim_media_data import text_to_base64
import aiohttp,tempfile
from moviepy.editor import VideoFileClip

# Vision API 설정
VISION_ENDPOINT = os.environ.get("VISION_ENDPOINT")
# VISION_SUBSCRIPTION_KEY = os.environ.get("VISION_SUBSCRIPTION_KEY")
VISION_SECRET_NAME = os.environ.get("VISION_SECRET_NAME")
VISION_SUBSCRIPTION_KEY = get_secret_from_key_vault(VISION_SECRET_NAME)
VISION_API_URL = f'{VISION_ENDPOINT}{os.environ.get("VISION_API_PATH")}'

AZURE_SEARCH_ENDPOINT = os.environ.get("AZURE_SEARCH_ENDPOINT")
AZURE_SEARCH_SECRET_NAME = os.environ.get("AZURE_SEARCH_SECRET_NAME")
AZURE_SEARCH_API_KEY = get_secret_from_key_vault(AZURE_SEARCH_SECRET_NAME)
# AZURE_SEARCH_API_KEY = os.environ.get("AZURE_SEARCH_API_KEY")
AZURE_SEARCH_API_VERSION = os.environ.get("AZURE_SEARCH_API_VERSION")
IMAGE_CHECK_INDEX_NAME = os.environ.get("IMAGE_CHECK_INDEX_NAME")

BLOB_CONTAINER_NAME = os.environ.get("BLOB_CONTAINER_NAME")


async def _upload_to_azure_search(documents, max_retries: int = 3):
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

async def _check_search(documents, max_retries: int = 3):
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

        
async def upload_embedding_async(semaphore,image_url,check:bool, max_retries=5):
    async with semaphore:
        if check:
            if await _check_search({"image_url": image_url}):
                return 
        headers = {
            "Ocp-Apim-Subscription-Key": VISION_SUBSCRIPTION_KEY
        }
        data = {
            'url': image_url
        }

        for attempt in range(1, max_retries + 1):
            async with aiohttp.ClientSession() as session:
                async with session.post(VISION_API_URL, headers=headers, json=data) as response:
                    if response.status == 200:
                        json_data = await response.json()
                        doc = {
                            "id": text_to_base64(image_url),
                            "image_url": image_url,
                            "imageVector": json_data["vector"]
                        }                        
                        await _upload_to_azure_search([doc])
                        return
                    elif response.status == 429:
                        wait_time = attempt * 2
                        print(f":hourglass: 429 too many requests. Retrying in {wait_time}s for {image_url}")
                        await asyncio.sleep(wait_time)
                    else:
                        error_text = await response.text()
                        print(f":x: 임베딩 실패: {response.status} {error_text} : {image_url}")
                        return

async def search_vector_for_url(image_url,threshold=0.95, max_retries: int = 3):
    for attempt in range(1, max_retries + 1):
        try:
            async with SearchClient(
                endpoint=AZURE_SEARCH_ENDPOINT,
                index_name=IMAGE_CHECK_INDEX_NAME,
                credential=AzureKeyCredential(AZURE_SEARCH_API_KEY)
            ) as client:
                results = await client.search(filter=f"image_url eq '{image_url}'",select="imageVector")
                output = [doc async for doc in results]
                if len(output) == 0:
                    return None

                return output[0]['imageVector']
                
        except Exception as e:
            print(f":경고: Azure Search upload attempt {attempt} failed: {e}")
            if attempt == max_retries:
                raise
            await asyncio.sleep(1 * attempt)

async def mp4_to_gif(mp4_url: str, az_blob, id: str, max_retries: int = 3) -> str:
    for attempt in range(1, max_retries + 1):
        try:
            # Step 1: 다운로드
            async with aiohttp.ClientSession() as session:
                async with session.get(mp4_url) as resp:
                    if resp.status != 200:
                        print(f"Failed to download video: {resp.status} url: {mp4_url}")
                        return None
                    video_bytes = await resp.read()
            # Step 2: 임시 mp4 저장
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp_video_file:
                tmp_video_file.write(video_bytes)
                tmp_video_path = tmp_video_file.name
            # Step 3: GIF로 변환
            gif_file_path = tmp_video_path.replace(".mp4", ".gif")

            clip = VideoFileClip(tmp_video_path)
            clip = clip.subclip(0, min(clip.duration, 10))  # 최대 10초까지만
            clip.write_gif(gif_file_path, fps=10)
            clip.reader.close()
            if clip.audio:
                clip.audio.reader.close_proc()
            # Step 4: GIF 파일을 Blob에 업로드
            file_name = f"{id}.gif"
            with open(gif_file_path, "rb") as gif_file:
                await az_blob.upload_blob(BLOB_CONTAINER_NAME, file_name, gif_file, content_type="image/gif")
            # Step 5: 결과 URL 반환
            gif_url = f"https://dev-img-kr.samsunggenai.com/{BLOB_CONTAINER_NAME}/{file_name}"
            # Step 6: 임시 파일 정리
            os.remove(tmp_video_path)
            os.remove(gif_file_path)
            return gif_url
        except Exception as e:
            print(f":경고: mp4_to_gif {attempt} failed: {e}")
            if attempt == max_retries:
                raise
            await asyncio.sleep(1 * attempt)

async def search_vector(image_vector,media_type,threshold=0.95, max_retries: int = 3):
    for attempt in range(1, max_retries + 1):
        try:
            async with SearchClient(
                endpoint=AZURE_SEARCH_ENDPOINT,
                index_name=IMAGE_CHECK_INDEX_NAME,
                credential=AzureKeyCredential(AZURE_SEARCH_API_KEY)
            ) as client:
                results = await client.search(select="image_url",
                                              filter=f"media_type eq '{media_type}'",
                                              vector_queries=[
                                                VectorizedQuery(
                                                    fields="imageVector",
                                                    vector=image_vector
                                                )
                                            ])
                return [doc async for doc in results if doc['@search.score'] >= threshold]
                
        except Exception as e:
            print(f":경고: Azure Search upload attempt {attempt} failed: {e}")
            if attempt == max_retries:
                raise
            await asyncio.sleep(1 * attempt)

async def get_embedding_async(image_url, max_retries=5):
    headers = {
        "Ocp-Apim-Subscription-Key": VISION_SUBSCRIPTION_KEY
    }
    data = {
        'url': image_url
    }

    for attempt in range(1, max_retries + 1):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(VISION_API_URL, headers=headers, json=data) as response:
                    if response.status == 200:
                        json_data = await response.json()
                    
                        return json_data["vector"]
                        
                    elif response.status == 429:
                        wait_time = attempt * 2
                        print(f":hourglass: 429 too many requests. Retrying in {wait_time}s for {image_url}")
                        await asyncio.sleep(wait_time)
                    else:
                        error_text = await response.text()
                        print(f":x: 임베딩 실패: {response.status} {error_text} : {image_url}")
                        raise
        except Exception as e:
            if attempt == max_retries:
                raise
            await asyncio.sleep(1 * attempt)


async def get_last_update_image(image_urls: list[str]):
    if not image_urls:
        return []
    
    num_urls = len(image_urls)
    placeholders = ', '.join(f'${i + 1}' for i in range(num_urls))

    query = f"""
        SELECT sys_upd_dtm,CASE 
                WHEN LEFT(img_url,1) = '/' THEN 'https://images.samsung.com/kdp' || img_url 
                ELSE img_url 
            END img_url
        FROM v_cpt
        WHERE 
            CASE 
                WHEN LEFT(img_url,1) = '/' THEN 'https://images.samsung.com/kdp' || img_url 
                ELSE img_url 
            END IN ({placeholders})
        ORDER BY sys_upd_dtm DESC LIMIT 1
    """

    async with DBManager(db_name='cloocusdb') as db:
        results = await db.fetchrow(query, *image_urls)
        return dict(results)

async def get_last_update_mp4(image_urls: list[str]):
    if not image_urls:
        return []
    
    num_urls = len(image_urls)
    placeholders = ', '.join(f'${i + 1}' for i in range(num_urls))

    query = f"""
        SELECT sys_upd_dtm,CASE 
                WHEN LEFT(mp4_url,1) = '/' THEN 'https://images.samsung.com/kdp' || mp4_url 
                ELSE mp4_url 
            END mp4_url
        FROM v_cpt
        WHERE 
            CASE 
                WHEN LEFT(mp4_url,1) = '/' THEN 'https://images.samsung.com/kdp' || mp4_url 
                ELSE mp4_url 
            END IN ({placeholders})
        ORDER BY sys_upd_dtm DESC LIMIT 1
    """

    async with DBManager(db_name='cloocusdb') as db:
        results = await db.fetchrow(query, *image_urls)
        return dict(results)
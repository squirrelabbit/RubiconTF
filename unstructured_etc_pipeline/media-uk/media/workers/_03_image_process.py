import os
import aiohttp, asyncio
import base64,tempfile
import traceback
from utils.data_postgres import DBManager
from media.modules.agent_base import BaseAgentModel
from pydantic import BaseModel, Field
from typing import Optional
from media.prompts.prompts import IMAGE_CHECK_SYSTEM_PROMPT
from moviepy.editor import VideoFileClip
from PIL import Image
from utils.data_blob import AzureBlobStorageAsync
from operator import attrgetter
from media.modules.pim_media_data import ImageDataOutput,unique_urls_media_type
from datetime import datetime
from tqdm import tqdm
import asyncpg
from urllib.parse import quote
from utils.common import get_secret_from_key_vault
from utils.log_manager import LogManager
import hashlib

PGDB_USERNAME = os.environ.get("PGDB_USERNAME")
PGDB_SECRET_NAME = os.getenv("PGDB_SECRET_NAME")
PG_PWD_KEY =quote(get_secret_from_key_vault(PGDB_SECRET_NAME))
PGDB_HOST = os.environ.get("PGDB_HOST")
PGDB_DBNAME = os.environ.get("PGDB_DBNAME")
PGDB_PORT = os.environ.get("PGDB_PORT")
PGDB_TABLE_NAME = os.environ.get("PGDB_TABLE_NAME")

BLOB_CONTAINER_NAME = os.environ.get("BLOB_CONTAINER_NAME")
BLOB_BASE_DOMAIN = os.environ.get("BLOB_BASE_DOMAIN")
IMAGE_TABLE_NAME = os.environ.get("IMAGE_TABLE_NAME")
IMAGE_LIST_PROC_TABLE_NAME = os.environ.get("IMAGE_LIST_PROC_TABLE_NAME")

MAX_CONCURRENT = 5
NUM_WORKERS = 50
semaphore = asyncio.Semaphore(MAX_CONCURRENT)


class ImageCheckerAnswer(BaseModel):
    valid_score: int = Field(default=None,description="제공된 이미지가 챗봇에서 사용하는 것이 적합한 특장점 이미지 인지 여부를 판단하세요. 1~5까지의 점수가 있으며 적합하지 않을 경우 1, 적합할수록 5에 가깝습니다. None으로 제공하지 말고 정확한 숫자로 제공하세요")
    reason: Optional[str] = Field(default=None,description="간략한 사유를 작성 하세요.")
    feature: Optional[str] = Field(default=None,description="제공된 이미지와 설명을 읽고 제품의 범위,특장점 및 기능 키워드에 대해 나열하세요")

class ImageCheckerAgent(BaseAgentModel):
    name = "image_checker"
    def __init__(self, **data):
        self.SYSTEM_PROMPT = IMAGE_CHECK_SYSTEM_PROMPT
        super().__init__(**data)

    @staticmethod
    def encode_image_to_base64(image_path: str) -> str:
        with open(image_path, "rb") as f:
            data = f.read()
        encoded = base64.b64encode(data).decode("utf-8")
        mime = "image/png" if image_path.endswith(".png") else "image/jpeg"
        return f"data:{mime};base64,{encoded}"
    
    async def generation_struct_pydantic(self, row:ImageDataOutput,az_blob,image_frame=None,image_type=None)-> ImageCheckerAnswer:
        product_info = {
            "Major category ": row.category1,
            "Medium category ": row.category2,
            "Sub category ": row.category3,
            "Name": row.display_name
        }
        image_info = []
        image_data = ""

        image_data = f"https://images.samsung.com/kdp{row.image_url}" if row.image_url.startswith('/') else row.image_url

        if image_type == "image":
            image_info.extend([
                {"type": "text", "text": f"alt text: {row.image_description}"},
                {"type": "image_url", "image_url": {"url": image_data}}
            ])
            
        elif image_type == "mp4" or image_type == "gif":           
            for idx,frame in enumerate(image_frame):
                image_caption = f"{str(idx)} 번째 이미지. 설명 : {row.image_description if image_type == 'gif' else row.image_description}"
                image_info.extend([
                    {"type": "text", "text": f"alt text: {image_caption}"},
                    {"type": "image_url", "image_url": {"url": frame}}
                ])
        else:
            return None
        
        return await super().generation_struct_pydantic(ImageCheckerAnswer, {"product_info":product_info, "image_info":image_info})   

async def get_target_url(source_url): 
    query = f"""
        SELECT target_url FROM {IMAGE_LIST_PROC_TABLE_NAME} WHERE source_url = $1;
    """
    async with DBManager(db_name='cloocusdb',pool=shared_pool) as db:
        record = await db.fetchrow(query,source_url)
    return dict(record) if record else None
    
async def check_pim_result(source_url): 
    query = f"""
        SELECT * FROM {IMAGE_TABLE_NAME} WHERE img_url = $1 OR mp4_url = $1;
    """
    async with DBManager(db_name='cloocusdb',pool=shared_pool) as db:
        record = await db.fetchrow(query,source_url)
    return dict(record) if record else None

async def upsert_image(db, data: dict):
    query = f"""
    INSERT INTO {IMAGE_TABLE_NAME} (
        pim_id, image_type, origin_img_url, origin_mp4_url,
        img_url, mp4_url, reason, valid_score, features,
        is_valid, last_update, upload_version
    )
    VALUES (
        $1, $2, $3, $4,
        $5, $6, $7, $8, $9,
        $10, $11, $12
    )
    ON CONFLICT (pim_id)
    DO UPDATE SET
        image_type = EXCLUDED.image_type,
        origin_img_url = EXCLUDED.origin_img_url,
        origin_mp4_url = EXCLUDED.origin_mp4_url,
        img_url = EXCLUDED.img_url,
        mp4_url = EXCLUDED.mp4_url,
        reason = EXCLUDED.reason,
        valid_score = EXCLUDED.valid_score,
        features = EXCLUDED.features,
        is_valid = EXCLUDED.is_valid,
        last_update = EXCLUDED.last_update,
        upload_version = EXCLUDED.upload_version;
    """
    await db.execute(
        query,
        data["pim_id"],
        data["image_type"],
        data["origin_img_url"],
        data["origin_mp4_url"],
        data["img_url"],
        data["mp4_url"],
        data["reason"],
        data["valid_score"],
        data["features"],
        data["is_valid"],
        data["last_update"],
        data["upload_version"],
    )
    
def compute_url_hash(url: str) -> str:
    if not url:
        return ""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:8]  # 짧게 8자리만

async def convert_worker(queue: asyncio.Queue, worker_id: int, progress_bar: tqdm):

    check_agent = ImageCheckerAgent()
    az_blob = AzureBlobStorageAsync()

    while True:      
        try:
            item = await queue.get()
            if item is None:
                queue.task_done()
                break
            
            image_type = item.image_type
            origin_data = item.image_url
            if origin_data.lower().endswith('.gif'):
                image_type = 'gif'
                image_type = 'image'

            target_url = await get_target_url(origin_data)

            image_data = target_url['target_url'] if target_url else origin_data
            check_data = await check_pim_result(image_data)
            check_result:ImageCheckerAnswer = None
            if check_data:
                check_result = ImageCheckerAnswer(
                    reason=check_data.get('reason'),
                    valid_score=check_data.get('valid_score'),
                    feature=check_data.get('features')
                )
            else:
                image_frame = None
                if image_type == "mp4" or image_type == "gif":
                    image_frame = await extract_frames(image_data,az_blob,item.id)
                
                results = [
                    await check_agent.generation_struct_pydantic(item, az_blob,image_frame,image_type)
                    for _ in range(3)
                ]
                valid_results = [r for r in results if r.valid_score is not None]
                check_result = min(valid_results, key=attrgetter("valid_score"))

            url_to_hash = origin_data if origin_data else image_data
            hash_part = compute_url_hash(url_to_hash)
            new_pim_id = f"{item.id}_{hash_part}"

            async with DBManager(db_name="cloocusdb",pool=shared_pool) as db:
                data = {
                        "pim_id": new_pim_id,
                        "image_type": item.image_type,
                        "origin_img_url": origin_data if image_type != 'mp4' else None,
                        "origin_mp4_url": origin_data if image_type == 'mp4' else None,
                        "img_url" : image_data if image_type != 'mp4' else None,
                        "mp4_url" : image_data if image_type == 'mp4' else None,
                        "reason" : check_result.reason,
                        "valid_score": check_result.valid_score,
                        "features": check_result.feature,
                        "is_valid": True if check_result.valid_score > 2 else False,
                        "last_update": datetime.strptime(item.modification_date,'%Y-%m-%d') if item.modification_date else None ,
                        "upload_version": version,
                }
                await upsert_image(db, data)
                # await db.insert(IMAGE_TABLE_NAME,data)

        except Exception as e:
            await LogManager.error(f"[WORKER-{worker_id}] {item.id} 처리 중 오류: {e} image_data: {image_data if image_data else ''}")
            traceback.print_exc()
        finally:
            progress_bar.update(1)
            queue.task_done()



async def extract_frames(mp4_url: str,az_blob,id:str, num_frames: int = 10) -> list[str]:
    # Step 1: 다운로드
    async with aiohttp.ClientSession() as session:
        async with session.get(mp4_url) as resp:
            if resp.status != 200:
                raise Exception(f"Failed to download video: {resp.status} url: {mp4_url}")
            video_bytes = await resp.read()

    # Step 2: 임시 파일 저장
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp_file:
        tmp_file.write(video_bytes)
        tmp_path = tmp_file.name

    # Step 3: moviepy로 프레임 추출
    clip = VideoFileClip(tmp_path)
    duration = clip.duration
    interval = duration / (num_frames + 1)

    frame_paths = []
    for i in range(1, num_frames + 1):
        t = i * interval
        frame = clip.get_frame(t)
        frame_file = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        Image.fromarray(frame).save(frame_file.name)

        with open(file=frame_file.name,mode="rb") as gif_file:
            file_name = f"{id}_{str(i)}.jpg"
            await az_blob.upload_blob(BLOB_CONTAINER_NAME,file_name,gif_file,content_type='image/jpg')
        frame_paths.append(f"{BLOB_BASE_DOMAIN}/{BLOB_CONTAINER_NAME}/{file_name}")
    clip.reader.close()
    if clip.audio:
        clip.audio.reader.close_proc()

    return frame_paths

async def monitor(queue: asyncio.Queue):
    try:
        while True:
            remaining = queue.qsize()
            await LogManager.info(f"[MONITOR] 남은 작업 수: {remaining}")
            await asyncio.sleep(5)
    except asyncio.CancelledError:
        await LogManager.info("[MONITOR] 모니터링 태스크 종료됨.")

async def process_image_check(ver):
    global shared_pool
    global version
    _, current_version = ver
    version = current_version

    shared_pool = await asyncpg.create_pool(
        f"postgresql://{PGDB_USERNAME}:{PG_PWD_KEY}@{PGDB_HOST}:{PGDB_PORT}/cloocusdb",
        min_size=5,
        max_size=30,
        timeout=30
    )
    
    query = f"""SELECT * FROM {PGDB_TABLE_NAME} order by update_date desc;"""
    
    async with DBManager(db_name=PGDB_DBNAME) as db:
        records = await db.fetch(query)
        pim_results = [dict(record) for record in records]
    uq_img = await unique_urls_media_type(pim_results,'image')
    uq_mp4 = await unique_urls_media_type(pim_results,'mp4')
    
    media_data = []

    media_data.extend(uq_img)
    media_data.extend(uq_mp4)

    queue = asyncio.Queue()

    for row in media_data:
        await queue.put(row)

    for _ in range(NUM_WORKERS):
        await queue.put(None)
                
    progress_bar = tqdm(total=len(media_data), desc="총 작업 수", unit="건")
    # convert_worker에 tqdm 전달
    workers = [asyncio.create_task(convert_worker(queue=queue, worker_id=i, progress_bar=progress_bar)) for i in range(NUM_WORKERS)]
    monitor_task = asyncio.create_task(monitor(queue))
    await queue.join()  
    monitor_task.cancel()
    await asyncio.gather(*workers, return_exceptions=True)
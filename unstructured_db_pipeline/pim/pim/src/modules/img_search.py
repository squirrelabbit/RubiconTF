import os
import logging
from urllib.parse import urlparse
from azure.cosmos.aio import CosmosClient
from azure.cosmos import exceptions, PartitionKey
from src.modules.ocr_client import analyze_image_url, process_gif_with_ocr
from src.modules.inference_img import get_inference
from src.models.feature_model import IndexBase
from datetime import datetime
import uuid
from utils.common import get_secret_from_key_vault

logger = logging.getLogger("app_logger")

COSMOS_ENDPOINT = os.environ.get("COSMOS_ENDPOINT")
COSMOS_DB_SECRET_NAME = os.environ.get("COSMOS_DB_SECRET_NAME")
COSMOS_KEY = get_secret_from_key_vault(COSMOS_DB_SECRET_NAME)
COSMOS_DB_NAME = os.environ.get("COSMOS_DB_NAME")
COSMOS_CONTAINER_NAME = os.environ.get("COSMOS_IMG_CONTAINER_NAME")
# Cosmos DB 클라이언트 생성
client = CosmosClient(COSMOS_ENDPOINT, COSMOS_KEY)
database = client.get_database_client(COSMOS_DB_NAME)
container = database.get_container_client(COSMOS_CONTAINER_NAME)

async def get_or_upload_alt(src, old_alt="", row=None, chunk=""):
    """
    Cosmos DB에서 'src' URL로 문서를 조회하고, 존재하지 않으면 OCR과 Inference 후 저장.
    """
    new_caption = old_alt  # 기본적으로 기존 alt 값을 유지
    try:
        # Step 1: Cosmos DB에서 'blob_path'가 'src'인 데이터 검색
        # logger.info(f"Searching for src in Cosmos DB: {src}")
        query = f"SELECT * FROM c WHERE c.blob_path = @blob_path"
        parameters = [{"name": "@blob_path", "value": src}]
        items = []
        async for item in container.query_items(query=query, parameters=parameters):
            items.append(item)
            
        if items:
            for item in items:
                new_caption_candidate = item.get("new_caption", "").strip()
                if new_caption_candidate:
                    # logger.info(f"Found existing document for src: {src} with new_caption: {new_caption_candidate}")
                    return new_caption_candidate
        # Step 2: OCR 및 Inference 수행
        # logger.info(f"Creating OCR: {src}. Processing OCR and generating new_caption.")
        ocr = ""
        # 이미지 확장자 확인 (GIF 처리 여부)
        ext = os.path.splitext(urlparse(src).path)[-1].lower()
        if ext == ".gif":
            ocr = await process_gif_with_ocr(src)
        elif ext ==".svg":
            pass 
        else:
            ocr = await analyze_image_url(src)
        index_data = IndexBase(row, chunk=chunk)
        # Inference 수행
        inference_data = index_data.to_inference_data(src, old_alt, ocr, chunk)
        new_caption = await get_inference(inference_data)
        # Step 3: Cosmos DB에 저장
        upload_data = {
            "id": str(uuid.uuid4()),  # UUID 생성
            "blob_path": src,
            "old_caption": old_alt,
            "ocr_text": ocr,
            "new_caption": new_caption,
            "created_at": datetime.utcnow().isoformat()
        }
        await container.upsert_item(upload_data)  # CosmosDB에 업서트 (존재하면 업데이트, 없으면 생성)
        # logger.info(f"Document uploaded successfully for src: {src}")
    except exceptions.CosmosHttpResponseError as e:
        logger.error(f"CosmosDB processing error for src: {src}, Error: {e}")
        new_caption = None
    except Exception as e:
         logger.error(f"processing img-data error for src: {src}, Error: {e}")
    return new_caption
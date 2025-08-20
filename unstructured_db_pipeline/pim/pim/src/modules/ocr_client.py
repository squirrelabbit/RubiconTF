import os
from PIL import Image,UnidentifiedImageError
import aiohttp
from io import BytesIO
import re
import base64
import cairosvg
from azure.core.credentials import AzureKeyCredential
from azure.ai.documentintelligence.aio import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import ( AnalyzeResult, DocumentAnalysisFeature, AnalyzeDocumentRequest )
from utils.common import get_secret_from_key_vault

import logging

logger = logging.getLogger("app_logger")


DI_ENDPOINT = os.environ['DI_ENDPOINT']
DI_SECRET_NAME = os.environ.get("DI_SECRET_NAME")
DI_KEY = get_secret_from_key_vault(DI_SECRET_NAME)

async def fetch_bytes(url):
    """ 주어진 URL에서 바이너리 데이터를 메모리로 직접 가져옵니다. """
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            response.raise_for_status()
            return await response.read()

def validate_and_process_image(image_bytes, file_extension):
    """이미지를 검증하고 필요한 경우 크기를 조정하거나 SVG를 변환합니다."""
    max_size = 10240  # 최대 허용 크기 (픽셀)
    min_size = 50     # 최소 허용 크기 (픽셀)

    if file_extension == ".svg":
        # SVG를 PNG로 변환
        try:
            image_bytes = cairosvg.svg2png(bytestring=image_bytes)
        except Exception as e:
            raise ValueError(f"Failed to convert SVG to PNG: {e}")
        pass

    try:
        with Image.open(BytesIO(image_bytes)) as img:
            width, height = img.size

            # 이미지 크기 검증 및 조정
            if width > max_size or height > max_size or width < min_size or height < min_size:
                if width > max_size or height > max_size:
                    new_width = min(max(width, height), max_size)
                    new_height = min(max(width, height), max_size)
                elif width < min_size or height < min_size:
                    new_width = max(min(width, height), min_size)
                    new_height = max(min(width, height), min_size)

                new_width = min(max(width, height), max_size)
                new_height = min(max(width, height), max_size)
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                buffer = BytesIO()
                img.save(buffer, format="JPEG", quality=95)
                return buffer.getvalue()

        return image_bytes
    except UnidentifiedImageError:
        raise ValueError("File format is not supported or image is corrupted.")

def extract_unique_frames_from_gif(gif_bytes):
    """
    주어진 이미지에서 중복되지 않는 프레임만 추출합니다.
    GIF가 아니면 단일 이미지로 처리
    반환값: PIL Image 리스트
    """
    frames = []
    previous_frame_data = None
    with Image.open(BytesIO(gif_bytes)) as img:
        if img.format != "GIF":
            # 단일 이미지일 경우 하나만 리턴
            return [img.convert("RGB")]
        for frame_number in range(getattr(img, "n_frames", 1)):
            try:
                img.seek(frame_number)
                current_frame = img.convert("RGB")
                frame_data = current_frame.tobytes()
                if previous_frame_data != frame_data:
                    frames.append(current_frame.copy())
                    previous_frame_data = frame_data
            except EOFError:
                break
    return frames

def pil_image_to_base64(pil_img):
    """ PIL 이미지를 base64로 인코딩하여 문자열로 반환합니다. """
    buffer = BytesIO()
    pil_img.save(buffer, format="JPEG", quality=95)
    encoded = base64.b64encode(buffer.getvalue()).decode('utf-8')
    return encoded


async def analyze_image_base64(pil_img):
    """ PIL 이미지를 base64로 인코딩한 뒤 OCR 분석합니다. """
    base64_data = pil_image_to_base64(pil_img)
    async with DocumentIntelligenceClient(
        endpoint=DI_ENDPOINT,
        credential=AzureKeyCredential(DI_KEY)
    ) as client:
        poller = await client.begin_analyze_document(
            model_id="prebuilt-layout",
            analyze_request=AnalyzeDocumentRequest(bytes_source=base64_data)  # 수정됨
        )
        result: AnalyzeResult = await poller.result()
        return result.content

def remove_duplicate_sentences(text_list):
    """
    주어진 텍스트 리스트에서 중복 문장을 제거하여 반환합니다.
    문장은 newline(\n) 기준으로 나눕니다.
    """
    unique_sentences = set()
    result = []
    for text in text_list:
        sentences = re.split(r'[\n]', text)
        for sentence in sentences:
            cleaned = sentence.strip()
            if cleaned and cleaned not in unique_sentences:
                unique_sentences.add(cleaned)
                result.append(cleaned)
    return result

MIN_WIDTH = 50
MIN_HEIGHT = 50
MAX_WIDTH = 2000
MAX_HEIGHT = 2000

def resize_image(image):
    image = image.convert("RGB")
    width, height = image.size
    # 너무 작으면 OCR 수행 안 함
    if width < MIN_WIDTH or height < MIN_HEIGHT:
        return None
    image = image.copy()  # 원본 보호
    if image.width > MAX_WIDTH or image.height > MAX_HEIGHT:
        image.thumbnail((MAX_WIDTH, MAX_HEIGHT), Image.Resampling.LANCZOS)
    return image

async def process_gif_with_ocr(gif_url):
    """ GIF 파일에 대해 프레임 추출 후 OCR 수행 및 중복 문장 제거 """
    gif_bytes = await fetch_bytes(gif_url)
    frames = extract_unique_frames_from_gif(gif_bytes)
    ocr_texts = []
    for idx, frame in enumerate(frames):
        logger.warning(f"[DEBUG] Original Frame {idx} size: {frame.size}")

        resized_frame = resize_image(frame)
        if resized_frame is None:
            logger.warning(f"[SKIP] Frame {idx} too small, skipping.")
            continue
        text = await analyze_image_base64(resized_frame)
        ocr_texts.append(text)
    # 중복 문장 제거
    return "\n".join(remove_duplicate_sentences(ocr_texts))

async def analyze_image_url(file_url):
    """이미지 URL에 대해 OCR 분석 수행."""
    try:
        # 파일 바이너리 가져오기
        file_bytes = await fetch_bytes(file_url)
        file_extension = file_url.split(".")[-1].lower()

        # 이미지 검증 및 처리
        processed_bytes = validate_and_process_image(file_bytes, file_extension)

        # Azure 분석 요청
        async with DocumentIntelligenceClient(
            endpoint=DI_ENDPOINT,
            credential=AzureKeyCredential(DI_KEY)
        ) as client:
            base64_data = base64.b64encode(processed_bytes).decode('utf-8')
            poller = await client.begin_analyze_document(
                model_id="prebuilt-layout",
                analyze_request=AnalyzeDocumentRequest(bytes_source=base64_data)  # 수정됨
            )

            result: AnalyzeResult = await poller.result()
            return result.content

    except ValueError as e:
        logger.error(f"Validation error for file: {file_url}, Error: {e}")
        return ""
    except Exception as e:
        logger.error(f"Error analyzing image URL: {file_url}, Error: {e}")
        return ""
import cairosvg
import base64
from io import BytesIO
from PIL import Image, UnidentifiedImageError, ImageEnhance
import aiohttp
from azure.core.credentials import AzureKeyCredential
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest, ContentFormat
from utils.common import get_secret_from_key_vault
import os

# Azure 설정
DI_ENDPOINT = os.environ['DI_ENDPOINT']
DI_SECRET_NAME = os.environ.get("DI_SECRET_NAME")
DI_KEY = get_secret_from_key_vault(DI_SECRET_NAME)

# load_dotenv(override=True)


async def fetch_bytes(url):
    """주어진 URL에서 바이너리 데이터를 메모리로 직접 가져옵니다."""
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            response.raise_for_status()
            return await response.read()
        
def validate_and_process_image(image_bytes, file_extension):
    """
    이미지를 검증하고 필요한 경우 크기를 조정하거나,
    높이가 5000px 초과하면 2000px 단위로 분할하여 반환합니다.
    """
    max_size = 10000  # 최대 허용 크기 (픽셀)
    min_size = 50     # 최소 허용 크기 (픽셀)
    split_height = 2000
    if file_extension.lower() == ".svg":
        try:
            image_bytes = cairosvg.svg2png(bytestring=image_bytes)
        except Exception as e:
            raise ValueError(f"Failed to convert SVG to PNG: {e}")
    try:
        with Image.open(BytesIO(image_bytes)) as img:
            width, height = img.size
            
            if img.mode == 'P':
                img = img.convert('RGBA')
                
            # contrast 높이기
            img = ImageEnhance.Contrast(img).enhance(1.8)
            # sharpeness 높이기
            img = ImageEnhance.Sharpness(img).enhance(2.0)
            
            # 5000px 초과시 분할
            if height > 5000:
                byte_chunks = []
                for i in range(0, height, split_height):
                    box = (0, i, width, min(i + split_height, height))
                    cropped = img.crop(box)
                    if cropped.mode in ('RGBA', 'LA', 'P'):
                        cropped = cropped.convert('RGB')
                    buffer = BytesIO()
                    cropped.save(buffer, format="JPEG", quality=95)
                    buffer.seek(0)
                    byte_chunks.append(buffer.getvalue())
                return "split", byte_chunks
            
            # 크기 검증 및 리사이즈
            if width > max_size or height > max_size or width < min_size or height < min_size:
                if width > max_size or height > max_size:
                    scale = max(width, height) / max_size
                    new_width = int(width / scale)
                    new_height = int(height / scale)
                else:
                    scale = min(width, height) / min_size
                    new_width = int(width / scale)
                    new_height = int(height / scale)
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                
            if img.mode in ('RGBA', 'LA', 'P'):
                img = img.convert('RGB')
            buffer = BytesIO()
            img.save(buffer, format="JPEG", quality=95)
            buffer.seek(0)
            
            return "resized", buffer.getvalue()
    except UnidentifiedImageError:
        raise ValueError("File format is not supported or image is corrupted.")
    
async def analyze_document(file_url):
    """
    파일 URL을 불러와서 Azure Document Intelligence로 분석합니다.
    길이가 긴 이미지는 분할하여 각각 분석합니다.
    """
    file_bytes = await fetch_bytes(file_url)
    file_extension = '.' + file_url.split(".")[-1].lower()
    if file_extension in [".jpg", ".jpeg", ".png", ".svg", ".bmp", ".gif"]:
        status, processed = validate_and_process_image(file_bytes, file_extension)
    elif file_extension == ".pdf":
        status, processed = "regular", file_bytes
    else:
        raise ValueError(f"Unsupported file extension: {file_extension}")
    
    client = DocumentIntelligenceClient(DI_ENDPOINT, AzureKeyCredential(DI_KEY))
    if status == "split":
        # 분할된 이미지 각각 분석 (여러 페이지 결과를 따로 가져올 수 있음)
        results = ""
        for part_bytes in processed:
            base64_data = base64.b64encode(part_bytes).decode('utf-8')
            poller = client.begin_analyze_document(
                "prebuilt-layout",
                AnalyzeDocumentRequest(bytes_source=base64_data),
                output_content_format=ContentFormat.MARKDOWN,
            )
            result = poller.result()
            results+= result.content
        return results
    else:
        # 하나짜리 파일 분석
        base64_data = base64.b64encode(processed).decode('utf-8')
        poller = client.begin_analyze_document(
            "prebuilt-layout",
            AnalyzeDocumentRequest(bytes_source=base64_data),
            output_content_format=ContentFormat.MARKDOWN,
        )
        result = poller.result()
        return result.content
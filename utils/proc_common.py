import os
from langchain_openai import AzureOpenAIEmbeddings
from azure.core.credentials import AzureKeyCredential
from azure.ai.documentintelligence.aio import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeResult, DocumentAnalysisFeature,ContentFormat,AnalyzeDocumentRequest
import base64
from utils.task_info import SeedData, TaskStatus, TaskType
from utils.data_cosmos import ContainerBaseModel,WorkerLogContainer
from utils.common import get_secret_from_key_vault
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
import openai

AZURE_OPENAI_EMBEDDING_API_VERSION = os.environ["AZURE_OPENAI_EMBEDDING_API_VERSION"]
AZURE_OPENAI_EMBEDDING_ENDPOINT = os.environ["AZURE_OPENAI_EMBEDDING_ENDPOINT"]
AZURE_OPENAI_EMBEDDING_SECRET_NAME = os.environ.get("AZURE_OPENAI_EMBEDDING_SECRET_NAME")
AZURE_OPENAI_EMBEDDING_API_KEY = get_secret_from_key_vault(AZURE_OPENAI_EMBEDDING_SECRET_NAME)
# AZURE_OPENAI_EMBEDDING_API_KEY = os.environ["AZURE_OPENAI_EMBEDDING_API_KEY"]
AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME = os.environ["AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME"]

DI_ENDPOINT = os.environ['DI_ENDPOINT']
DI_SECRET_NAME = os.environ.get("DI_SECRET_NAME")
DI_KEY = get_secret_from_key_vault(DI_SECRET_NAME)

@retry(
        wait=wait_exponential(multiplier=1, min=4, max=20),
        stop=stop_after_attempt(5),
        retry=retry_if_exception_type(openai.RateLimitError)
)
async def aembedding_data(data):
    try:
        embedder = AzureOpenAIEmbeddings(azure_endpoint=AZURE_OPENAI_EMBEDDING_ENDPOINT, api_key= AZURE_OPENAI_EMBEDDING_API_KEY, deployment=AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME) 
        return await embedder.aembed_query(data if data!="" else "-------")
    except openai.RateLimitError as e:
        raise e
    except Exception as e:
        raise Exception(f"임베딩 처리 중 오류 발생: {e}")

@retry(
        wait=wait_exponential(multiplier=1, min=4, max=20),
        stop=stop_after_attempt(5),
        retry=retry_if_exception_type(openai.RateLimitError)
)
def embedding_data(data):
    try:
        embedder = AzureOpenAIEmbeddings(azure_endpoint=AZURE_OPENAI_EMBEDDING_ENDPOINT, api_key= AZURE_OPENAI_EMBEDDING_API_KEY, deployment=AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME) 
        return embedder.embed_query(data if data!="" else "-------")
    except openai.RateLimitError as e:
        raise e
    except Exception as e:
        raise Exception(f"임베딩 처리 중 오류 발생: {e}")

async def analyze_layout_page(file_url: str):
    """
    레이아웃 분석을 수행하고 각 페이지의 레이아웃 데이터를 반환합니다.
    """
    offset = 0
    page_map = []

    async with DocumentIntelligenceClient(
        endpoint=DI_ENDPOINT,
        credential=AzureKeyCredential(DI_KEY)
    ) as client:
        poller = await client.begin_analyze_document(
            model_id="prebuilt-layout",
            analyze_request=AnalyzeDocumentRequest(url_source=file_url),
            features=[DocumentAnalysisFeature.OCR_HIGH_RESOLUTION],
            output_content_format=ContentFormat.MARKDOWN
        )
        result: AnalyzeResult = await poller.result()

        output = []

        for page_num, page in enumerate(result.pages):
            page_offset = page.spans[0].offset
            page_length = page.spans[0].length
            chunk = result.content[page_offset:page_offset + page_length]
            offset += len(chunk)

            output.append((chunk, page_num + 1))

    return output


def text_to_base64(text):
    bytes_data = text.encode('utf-8')
    base64_encoded = base64.urlsafe_b64encode(bytes_data)
    base64_text = base64_encoded.decode('utf-8')

    return base64_text


from typing import TypeVar,Type

ContainerT = TypeVar("ContainerT", bound="ContainerBaseModel")
async def change_status(system_name,status:TaskStatus,task_type:TaskType,seed:SeedData=None,seed_container:Type[ContainerT]=None):
    if seed_container and seed:
        seed.next_action = False
        seed.status = status
        async with seed_container() as db:
            await db.upsert(seed)

    async with WorkerLogContainer() as log:
        await log.save_log(system_name,status.value,task_type.value)
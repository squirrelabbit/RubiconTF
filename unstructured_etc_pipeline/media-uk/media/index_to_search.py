from media.proc_media_common import MediaSearchContainer, MediaSearch
import logging
import asyncio
from tqdm import tqdm
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential
import os
from utils.common import get_secret_from_key_vault

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logging.getLogger("azure").setLevel(logging.WARNING)
logging.getLogger("azure.core.pipeline.policies.http_logging_policy").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

AZURE_SEARCH_ENDPOINT = os.environ.get("AZURE_SEARCH_ENDPOINT")
AZURE_SEARCH_SECRET_NAME = os.environ.get("AZURE_SEARCH_SECRET_NAME")
AZURE_SEARCH_API_KEY = get_secret_from_key_vault(AZURE_SEARCH_SECRET_NAME)
AZURE_SEARCH_API_VERSION = os.environ.get("AZURE_SEARCH_API_VERSION")
AZURE_SEARCH_INDEX_NAME = os.environ['SYSTEM_NAME']

loaded_list = []
credential = AzureKeyCredential(AZURE_SEARCH_API_KEY)

search_client = SearchClient(
    endpoint=AZURE_SEARCH_ENDPOINT, 
    index_name="dev-pim", 
    credential=credential)

async def migrate_data(current_version):
    logging.info(f"=== 데이터 마이그레이션 시작 (version: {current_version}) ===")
    # items = search_client.search(search_text="*", include_total_count=True, order_by=["id asc"])
    # logging.info(f"총 {items.get_count()}개의 문서 조회됨")
    async with MediaSearchContainer() as cosmos:
        query = """
        SELECT * FROM c
        WHERE c.system_name = @system_name
        AND c.version = @version
        """
        params = [
            {"name": "@system_name", "value": "dev-pim"},
            {"name": "@version", "value": "250604"},
        ]
        container = await cosmos.get_container()
        existing_docs = [doc async for doc in container.query_items(query=query, parameters=params)]
        logging.info(f"총 {len(existing_docs)}개의 문서 조회됨")

        if existing_docs:
            for doc in tqdm(existing_docs):
                try:
                    index = MediaSearch(**doc)
                    index.version = current_version
                    await cosmos.upsert(index)
                except Exception as e:
                    logging.error(f"문서 처리 중 오류 발생 (id: {doc.get('id', 'unknown')}): {str(e)}")
    logging.info("=== 마이그레이션 작업 완료 ===")

if __name__ == "__main__":
    asyncio.run(migrate_data("250602"))
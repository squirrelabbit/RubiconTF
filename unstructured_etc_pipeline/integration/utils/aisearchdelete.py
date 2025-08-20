import asyncio
import logging
from azure.search.documents.aio import SearchClient
from azure.core.credentials import AzureKeyCredential
import utils.constants as VARIABLE
from utils.dbsearch import history_insert
import os
from utils.common import get_secret_from_key_vault
from dotenv import load_dotenv
# load_dotenv(override=True)
INTEGRATION_INDEX_NAME = os.getenv("INTEGRATION_INDEX_NAME")

async def delete_old_versions_aisearch(idx_nm, current_version):
    current_version = current_version[:6]
    endpoint = os.getenv("AZURE_SEARCH_ENDPOINT")
    AZURE_SEARCH_SECRET_NAME = os.environ.get("AZURE_SEARCH_SECRET_NAME")
    api_key = get_secret_from_key_vault(AZURE_SEARCH_SECRET_NAME)
    credential = AzureKeyCredential(api_key)
    logging.info("ai search delete logic start")
    async with SearchClient(endpoint=endpoint, index_name=idx_nm, credential=credential) as client:
        # Fetch all documents with a version less than the current version
        filter_str = f"version lt '{current_version}'"
        local_count = 0
        while True:
            results = await client.search(search_text="*", filter=filter_str, select=["id"], top=1000)
            documents_to_delete = [{"id": result["id"]} async for result in results]
            if not documents_to_delete:
                break
            try:
                await client.delete_documents(documents=documents_to_delete)
                logging.info(f"IDX_NM : {idx_nm} / Deleted {len(documents_to_delete)} documents with version less than {current_version}")
                local_count += len(documents_to_delete)
            except Exception as e:
                logging.info(f"Error deleting documents, error: {e}")
        if not local_count  == 0:
            history_insert(VARIABLE.WORK_TYPE_LOCAL_DELETE,idx_nm,current_version,local_count)

    if 'media' not in idx_nm:             
        async with SearchClient(endpoint=endpoint, index_name=INTEGRATION_INDEX_NAME, credential=credential) as client:
            # Fetch all documents with a version less than the current version
            filter_str = f"system_name eq '{idx_nm}' and version lt '{current_version}'"
            integration_count = 0
            while True:
                results = await client.search(search_text="*", filter=filter_str, select=["id"], top=1000)
                documents_to_delete = [{"id": result["id"]} async for result in results]
                if not documents_to_delete:
                    break
                try:
                    await client.delete_documents(documents=documents_to_delete)
                    logging.info(f"IDX_NM : {INTEGRATION_INDEX_NAME} / Deleted {len(documents_to_delete)} documents with version less than {current_version}")
                    integration_count += len(documents_to_delete)
                except Exception as e:
                    logging.info(f"Error deleting documents, error: {e}")
            if not integration_count  == 0:
                history_insert(VARIABLE.WORK_TYPE_INTEGRATION_DELETE,idx_nm,current_version,integration_count)
    logging.info("ai search delete logic end")
# Example usage
# asyncio.run(delete_old_versions("your_index_name", "250526"))
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential
from utils.dbsearch import history_insert
from dotenv import load_dotenv
import utils.constants as VARIABLE
import logging
import os
from utils.common import get_secret_from_key_vault
# load_dotenv(override=True)
AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")
AZURE_SEARCH_SECRET_NAME = os.environ.get("AZURE_SEARCH_SECRET_NAME")
AZURE_SEARCH_API_KEY = get_secret_from_key_vault(AZURE_SEARCH_SECRET_NAME)
AZURE_SEARCH_API_VERSION = os.getenv("AZURE_SEARCH_API_VERSION")
INTEGRATION_INDEX_NAME = os.getenv("INTEGRATION_INDEX_NAME")
import time

def check_local_integration_sync_status(index_name, version):
    try:
        logging.info(f"[check_local_integration_sync_status] {index_name}   {version}")
        attempts = 0
        while attempts < 10:
            search_client = SearchClient(endpoint=AZURE_SEARCH_ENDPOINT,
                                        index_name=index_name,
                                        credential=AzureKeyCredential(AZURE_SEARCH_API_KEY))
            local_results = search_client.search(
                search_text="*",
                filter=f"system_name eq '{index_name}' and version eq '{version}'",
                include_total_count=True,
                top=0
            )
            
            logging.info(f"[local index count] calculating...")
            local_count = local_results.get_count()
            logging.info(f"[local index count] {str(local_count)} ")
            search_client = SearchClient(endpoint=AZURE_SEARCH_ENDPOINT,
                                        index_name=INTEGRATION_INDEX_NAME,
                                        credential=AzureKeyCredential(AZURE_SEARCH_API_KEY))
            integration_results = search_client.search(
                search_text="*",
                filter=f"system_name eq '{index_name}' and version eq '{version}'",
                include_total_count=True,
                top=0
            )
            logging.info(f"[integration index count] calculating...")
            integration_count = integration_results.get_count()
            logging.info(f"[integration index count] {str(integration_count)}")

            if local_count == integration_count:
                logging.info(f"integration index migration success")
                history_insert(VARIABLE.WORK_TYPE_INTEGRATION,index_name,version,integration_count)
                return True

            attempts += 1
            time.sleep(5)
    except Exception as e :
        logging.error(e)
    logging.info("integration index migration failed")
    return False
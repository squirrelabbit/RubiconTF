from azure.cosmos import CosmosClient, exceptions
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential
from dotenv import load_dotenv
from utils.dbsearch import history_insert
import logging
import os
import time
import utils.constants as VARIABLE
from utils.common import get_secret_from_key_vault
# load_dotenv(override=True)
COSMOS_ENDPOINT = os.getenv("COSMOS_ENDPOINT")
COSMOS_DB_SECRET_NAME = os.environ.get("COSMOS_DB_SECRET_NAME")
COSMOS_KEY = get_secret_from_key_vault(COSMOS_DB_SECRET_NAME)
DATABASE_NAME = os.getenv("DATABASE_NAME")
SEARCH_CONTAINER_NAME = os.getenv("SEARCH_CONTAINER_NAME")
AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")
AZURE_SEARCH_SECRET_NAME = os.environ.get("AZURE_SEARCH_SECRET_NAME")
AZURE_SEARCH_API_KEY = get_secret_from_key_vault(AZURE_SEARCH_SECRET_NAME)
AZURE_SEARCH_API_VERSION = os.getenv("AZURE_SEARCH_API_VERSION")

def local_search_cont_sync_check(system_name, version):
    attempts = 0
    while attempts < 10:
        # 클라이언트 생성
        client = CosmosClient(COSMOS_ENDPOINT, COSMOS_KEY)

        # 데이터베이스 및 컨테이너 선택
        database = client.get_database_client(DATABASE_NAME)
        container = database.get_container_client(SEARCH_CONTAINER_NAME)

        # 쿼리 실행
        query = f"SELECT VALUE COUNT(1) FROM c WHERE c.system_name = '{system_name}' and c.version = '{version}'"
        logging.info("['cosmosdb execute']"+query)
        
        cosmoscnt = list(container.query_items(query=query, enable_cross_partition_query=True))[0]
        logging.info(f"[cosmosdb search cont] count :{str(cosmoscnt)}")
        search_client = SearchClient(endpoint=AZURE_SEARCH_ENDPOINT,
                                    index_name=system_name,
                                    credential=AzureKeyCredential(AZURE_SEARCH_API_KEY))
        local_results = search_client.search(
            search_text="*",
            include_total_count=True,
            filter=f"system_name eq '{system_name}' and version eq '{version}'",
            top=0
        )

        local_count = local_results.get_count()
        logging.info(f"[local index] count :{str(local_count)}")
        if cosmoscnt >= local_count :
            logging.info("cosmos migration success")
            history_insert(VARIABLE.WORK_TYPE_SEARCH,system_name,version,cosmoscnt)
            return True
        
        attempts += 1
        time.sleep(5)

    logging.info("cosmos migration failed")
    return False
        
def cosmos_check(system_name, version, seed_cont_name):
    # 클라이언트 생성
    #logging.info(system_name)
    #logging.info(version)
    client = CosmosClient(COSMOS_ENDPOINT, COSMOS_KEY)

    # 데이터베이스 및 컨테이너 선택
    database = client.get_database_client(DATABASE_NAME)
    container = database.get_container_client(seed_cont_name)

    # 쿼리 실행
    query = f"SELECT VALUE COUNT(1) FROM c WHERE c.system_name = '{system_name}' and c.version = '{version}'"
    no_with_status_items_count = list(container.query_items(query=query, enable_cross_partition_query=True))[0]
    #logging.info(no_with_status_items_count)
    query = f"SELECT VALUE COUNT(1) FROM c WHERE c.system_name = '{system_name}' and c.version = '{version}' and c.status = 'WAITING'"
    waiting_items_count = list(container.query_items(query=query, enable_cross_partition_query=True))[0]
    #logging.info(waiting_items_count)
    query = f"SELECT VALUE COUNT(1) FROM c WHERE c.system_name = '{system_name}' and c.version = '{version}' and c.status = 'IN_PROGRESS'"
    inprogress_status_items_count = list(container.query_items(query=query, enable_cross_partition_query=True))[0]
    #logging.info(inprogress_status_items_count)
    if no_with_status_items_count > 0 and waiting_items_count == 0 and inprogress_status_items_count == 0:
        history_insert(VARIABLE.WORK_TYPE_LOCAL,system_name,version,no_with_status_items_count)
        return True
    logging.info("[cosmos db] not complete")
    return False
import yaml
import os
from datetime import datetime
from dotenv import load_dotenv
from utils.common import get_secret_from_key_vault

load_dotenv(override=True)
IS_AZURE = os.getenv("WEBSITE_INSTANCE_ID") is not None

LANGUAGE = os.getenv("SYSTEM_LOCATION")
SYSTEM_NAME = os.getenv("CONFIG_NAME")
PGDB_SECRET_NAME = os.getenv("PGDB_SECRET_NAME")
PG_PWD_KEY = get_secret_from_key_vault(PGDB_SECRET_NAME)

DATABASE = {
    "host": os.getenv("PGDB_HOST"),
    "port": os.getenv("PGDB_PORT"),
    "database": os.getenv("PGDB_DBNAME"),
    "user": os.getenv("PGDB_USERNAME"),
    "password": PG_PWD_KEY,
    "table_name": os.getenv("PGDB_TABLE_NAME"),
}

API = {
    "base_url": os.getenv("API_BASE_URL"),
    "key": os.getenv("API_KEY"),
    "offer_base_url" : os.getenv("API_OFFER_BASE_URL")
}

AZURE_EMBEDDING_OPENAI = {
    "endpoint": os.getenv("AZURE_OPENAI_EMBEDDING_ENDPOINT"),
    "api_key": os.getenv("AZURE_OPENAI_EMBEDDING_API_KEY"),
    "deployment_name": os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME"),
}
AZURE_OPENAI = {
    "endpoint": os.getenv("AZURE_OPENAI_ENDPOINT"),
    "api_key": os.getenv("AZURE_OPENAI_API_KEY"),
    "api_version": os.getenv("OPENAI_API_VERSION"),
    "deployment_name": os.getenv("COMPLETIONS_MODEL"),
}
AZURE_SEARCH = {
    "endpoint": os.getenv("AZURE_SEARCH_ENDPOINT"),
    "api_key": os.getenv("AZURE_SEARCH_KEY"),
    "index_name": os.getenv("AZURE_SEARCH_INDEX_NAME"),
}
AZURE_IMG_SEARCH = {
    "endpoint": os.getenv("AZURE_IMG_SEARCH_ENDPOINT"),
    "api_key": os.getenv("AZURE_IMG_SEARCH_KEY"),
    "index_name": os.getenv("AZURE_IMG_SEARCH_INDEX_NAME"),
}

OUTPUT_DIR = "/tmp" if IS_AZURE else "output/"    
OUTPUT_FOLDER = os.path.join(os.getcwd(), f'{OUTPUT_DIR}/{SYSTEM_NAME}_{LANGUAGE}_{datetime.now().strftime("%Y%m%d")}')

USER ={
    "id": os.getenv("USER_ID"),
    "pwd": os.getenv("USER_PWD")
}

FMUSER ={
    "id": os.getenv("FMUSER_ID"),
    "pwd": os.getenv("FMUSER_PWD")
}
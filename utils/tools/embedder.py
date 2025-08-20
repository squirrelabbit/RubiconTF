from langchain_openai import AzureOpenAIEmbeddings
import os
from dotenv import load_dotenv
from tools.retriever_grpc import run_embedding
from utils.common import get_secret_from_key_vault
import asyncio
import openai

load_dotenv()

AZURE_OPENAI_EMBEDDING_ENDPOINT = os.environ["AZURE_OPENAI_EMBEDDING_ENDPOINT"]
AZURE_OPENAI_EMBEDDING_SECRET_NAME = os.environ.get("AZURE_OPENAI_EMBEDDING_SECRET_NAME")
AZURE_OPENAI_EMBEDDING_API_KEY = get_secret_from_key_vault(AZURE_OPENAI_EMBEDDING_SECRET_NAME)
# AZURE_OPENAI_EMBEDDING_API_KEY = os.environ["AZURE_OPENAI_EMBEDDING_API_KEY"]
AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME = os.environ["AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME"]


async def aoai_aembedding(data):
    embedder = AzureOpenAIEmbeddings(azure_endpoint=AZURE_OPENAI_EMBEDDING_ENDPOINT, api_key= AZURE_OPENAI_EMBEDDING_API_KEY, deployment=AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME)
    #print(data)
    while True:
        try:
            return await asyncio.wait_for(embedder.aembed_query(data), timeout=10.0)
        except asyncio.TimeoutError:
            print("Timeout occurred, retrying...")
            await asyncio.sleep(5)  # 5초 후 재시도
        except openai.RateLimitError as e:
            print("RateLimitError, retrying...")
            await asyncio.sleep(5)  # 5초 후 재시도
        except Exception as e:
            print(f"error {e}")

async def bge_embedding(data):
    #print(data)
    while True:
        try:
            result = await asyncio.wait_for(run_embedding(data), timeout=3.0)
            return result
        except asyncio.TimeoutError:
            print("Timeout occurred in bge_embedding, retrying...")
            await asyncio.sleep(5)  # 5초 후 재시도
        except Exception as e:
            print(f"error {e}")

async def bge_embedding_retry(text: str, *, retries: int = 1, timeout: float = 3.0):
    """Timeout 시 최대 `retries` 만큼 재시도"""
    for attempt in range(retries + 1):
        try:
            result = await asyncio.wait_for(run_embedding(text), timeout=timeout)
            if result:
                return result
            else:
                continue
        except asyncio.TimeoutError:
            if attempt < retries:
                print("Timeout occurred in bge_embedding, retrying...")
                continue
            print("Timeout occurred in bge_embedding, giving up.")
            return []
        except Exception as e:
            print(f"Embedding error: {e}")
            return []
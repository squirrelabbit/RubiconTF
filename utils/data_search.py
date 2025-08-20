from dataclasses import dataclass, field,fields
from typing import Optional, Type, List, TypeVar, Dict, Any
from enum import Enum
from datetime import datetime
from abc import ABC
import os,json
import aiohttp
import asyncio
from dotenv import load_dotenv
from utils.log_manager import LogManager
from utils.common import get_secret_from_key_vault
import random
from azure.search.documents import SearchClient
from azure.search.documents.aio import SearchClient as SearchClientAio
from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import HttpResponseError

load_dotenv(override=True)


AZURE_SEARCH_ENDPOINT = os.environ.get("AZURE_SEARCH_ENDPOINT")
AZURE_SEARCH_SECRET_NAME = os.environ.get("AZURE_SEARCH_SECRET_NAME")
AZURE_SEARCH_API_KEY = get_secret_from_key_vault(AZURE_SEARCH_SECRET_NAME)
# AZURE_SEARCH_API_KEY = os.environ.get("AZURE_SEARCH_API_KEY")
AZURE_SEARCH_API_VERSION = os.environ.get("AZURE_SEARCH_API_VERSION")
AZURE_SEARCH_INDEX_NAME = os.environ['SYSTEM_NAME']

T = TypeVar('T', bound='IndexBase')

@dataclass
class Product:
    product: Optional[str] = None
    model_code: List[str] = field(default_factory=list)
    def to_dict(self):
        return {
            "product": self.product,
            "model_code": self.model_code,
        }
@dataclass
class PartnerProduct:
    product: Optional[str] = None
    model_code: List[str] = field(default_factory=list)
    def to_dict(self):
        return {
            "product": self.product,
            "model_code": self.model_code,
        }
        
@dataclass
class IndexBase(ABC):
    id: Optional[str] = None
    original_id: Optional[str] = None # 버전 제외한 id
    system_name: Optional[str] = None
    version: Optional[str] = None
    bu: Optional[str] = None
    category1: Optional[str] = None
    category2: Optional[str] = None
    category3: Optional[str] = None
    title: Optional[str] = None
    content: Optional[str] = None
    answer: Optional[str] = None
    blob_path: Optional[str] = None
    chunk: Optional[str] = None
    semantic_title: Optional[str] = None
    semantic_summary: Optional[str] = None
    semantic_chunk: Optional[str] = None
    disclaimer: Optional[str] = None
    file_name: Optional[str] = None
    question: Optional[str] = None
    question_category: Optional[str] = None
    type: Optional[str] = None
    filter_id: Optional[str] = None
    chunk_seq: Optional[int] = None
    semantic_chunk_seq: Optional[int] = None
    display_seq: Optional[int] = None
    page_num: Optional[int] = None
    question_num: Optional[int] = None
    section_num: Optional[int] = None
    is_display: Optional[int] = None
    reg_date: Optional[str] = None
    disp_strt_dtm: Optional[str] = None
    disp_end_dtm: Optional[str] = None
    family_code: List[str] = field(default_factory=list)
    family_name: List[str] = field(default_factory=list)
    common_code: List[str] = field(default_factory=list)
    goods_id: List[str] = field(default_factory=list)
    goods_nm: List[str] = field(default_factory=list)
    img_data: List[str] = field(default_factory=list)
    model_group_code: List[str] = field(default_factory=list)
    model_code: List[str] = field(default_factory=list)
    model_name: List[str] = field(default_factory=list)
    product_model: List[str] = field(default_factory=list)
    products: List[Product] = field(default_factory=list)
    partner_products: List[PartnerProduct] = field(default_factory=list)
    embedding_chunk: List[float] = field(default_factory=list)
    embedding_semantic_bgechunk: List[float] = field(default_factory=list)
    embedding_semantic_bgetitle: List[float] = field(default_factory=list)


    def to_dict(self) -> dict:
    # def to_dict(self, embedding=True) -> dict:
        item_dict = {}
        for k, v in self.__dict__.items():
            if callable(v) or isinstance(v, type):  
                continue

            # 객체가 IndexBase, Product, PartnerProduct 등의 클래스라면 재귀적으로 to_dict 호출
            if isinstance(v, IndexBase) or isinstance(v, Product) or isinstance(v, PartnerProduct):
                item_dict[k] = v.to_dict()
            # 리스트 내부에 클래스를 포함하는 경우 처리
            elif isinstance(v, list) and v and isinstance(v[0], (IndexBase, Product, PartnerProduct)):
                item_dict[k] = [item.to_dict() for item in v]
            # Enum 처리
            elif isinstance(v, Enum):
                item_dict[k] = v.value
            elif hasattr(v, "to_dict"):
                item_dict[k] = v.to_dict()
            else:
                item_dict[k] = v

        return item_dict
    
    
    @classmethod
    def from_search_result(cls, data: Dict[str, Any], ignore_embedding=False):
        valid_field_names = {f.name for f in fields(cls)}
        filtered_data = {k: v for k, v in data.items() if k in valid_field_names}
        if ignore_embedding and "embedding_chunk" in filtered_data:
            filtered_data.pop("embedding_chunk")
            filtered_data.pop("embedding_semantic_chunk")
            filtered_data.pop("embedding_semantic_bgechunk")
        return cls(**filtered_data)



class SearchService:
    @staticmethod
    async def search(index:Type[T],category1=None,category2=None,category3=None,model_code=None,model_name=None,title=None,file_name=None,blob_path=None,id=None,ignore_embedding=False) -> List[T]:
        headers = {
            "Content-Type": "application/json",
            "api-key": AZURE_SEARCH_API_KEY,
        }
        params = {'api-version': AZURE_SEARCH_API_VERSION}
        
        payload = {"search": "*"}
        filter_condition = SearchService.set_filter(index, category1, category2, category3, model_code, model_name, title,file_name,blob_path,id)

        if filter_condition:  
            payload["filter"] = filter_condition


        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{AZURE_SEARCH_ENDPOINT}/indexes/{AZURE_SEARCH_INDEX_NAME}/docs/search",
                json=payload,
                headers=headers,
                params=params
            ) as response:
                response.raise_for_status()
                result = await response.json()
                return [index.from_search_result(data=doc,ignore_embedding=ignore_embedding) for doc in result.get("value", [])]

            
    @staticmethod
    def set_filter(index:Type[T],category1=None,category2=None,category3=None,model_code=None,model_name=None,title=None,file_name=None,blob_path=None,id=None) -> str:
        filter_str = []

        if category1:
            filter_str.append(f"category1 eq '{category1}'")
        if category2:
            filter_str.append(f"category2 eq '{category2}'")
        if category3:
            filter_str.append(f"category3 eq '{category3}'")
        if title:
            filter_str.append(f"title eq '{title}'")
        if file_name:
            filter_str.append(f"file_name eq '{file_name}'")
        if blob_path:
            filter_str.append(f"blob_path eq '{blob_path}'")
        if id:
            filter_str.append(f"id eq '{id}'")
        if model_code:
            if isinstance(index.model_code, str):
                filter_str.append(f"model_code eq '{model_code}'")
            elif isinstance(index.model_code, list):
                return f"model_code/any(c: c eq '{model_code}')"

        if model_name:
            if isinstance(index.model_name, str):
                filter_str.append(f"model_name eq '{model_name}'")
            elif isinstance(index.model_name, list):
                return f"model_name/any(c: c eq '{model_name}')"

        return " and ".join(filter_str)
    
    @staticmethod
    async def delete(index:IndexBase):
        try:
            search_client = SearchClient(
                endpoint=AZURE_SEARCH_ENDPOINT,
                index_name=AZURE_SEARCH_INDEX_NAME,
                credential=AzureKeyCredential(AZURE_SEARCH_API_KEY)
            )
            documents = [{"id":index.id}]
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, search_client.delete_documents, documents)
        except HttpResponseError as e:
            await LogManager.exception(e)
            raise
        except Exception as e:
            await LogManager.exception(e)
            raise   
        

    @staticmethod
    async def upload(index: IndexBase):
        try:
            # SearchClient 초기화
            search_client = SearchClient(
                endpoint=AZURE_SEARCH_ENDPOINT,
                index_name=AZURE_SEARCH_INDEX_NAME,
                credential=AzureKeyCredential(AZURE_SEARCH_API_KEY)
            )
            # 업로드할 문서 생성
            documents = [{**index.to_dict()}]
            # SDK는 기본적으로 비동기를 지원하지 않으므로, 쓰레드 풀로 실행
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, search_client.upload_documents, documents)
        except HttpResponseError as e:
            await LogManager.exception(e)
            raise
        except Exception as e:
            await LogManager.exception(e)
            raise
        
    @staticmethod
    async def upload_batch(index_list:List[IndexBase], batch_size:int, max_retries:int=5, initial_delay: int=2):
        """
        문서 목록을 배치 단위로 업로드합니다.
        지수 백오프 및 실패한 항목만 재시도하는 로직을 적용합니다.
        :param index_list: 업로드할 문서 객체 리스트
        :param batch_size: 한 번에 업로드할 배치 크기
        :param max_retries: 실패 시 최대 재시도 횟수
        :param initial_delay: 재시도 시 초기 대기 시간 (초)
        """
        async with SearchClientAio(
            endpoint=AZURE_SEARCH_ENDPOINT,
            index_name=AZURE_SEARCH_INDEX_NAME,
            credential=AzureKeyCredential(AZURE_SEARCH_API_KEY)
        ) as search_client:
            total_documents = len(index_list)
            for i in range(0, total_documents, batch_size):
                original_batch = index_list[i : i + batch_size]
                documents_to_upload = [{**index.to_dict()} for index in original_batch]
                current_batch_num = i // batch_size + 1
                for attempt in range(max_retries):
                    try:
                        # 업로드 시도
                        results = await asyncio.wait_for(search_client.upload_documents(documents=documents_to_upload), timeout=30.0  # 타임아웃을 넉넉하게 설정
                        )
                        results_list = list(results)
                        # 성공한 문서와 실패한 문서를 분리
                        succeeded_docs = [res for res in results_list if res.succeeded]
                        failed_docs = [res for res in results_list if not res.succeeded]
                        
                        # 모든 문서가 성공한 경우
                        if not failed_docs:
                            await LogManager.info(
                                f"[UPLOAD] 배치 {current_batch_num} 성공: {len(succeeded_docs)}/{len(documents_to_upload)} 문서 "
                                f"({i + len(original_batch)}/{total_documents} 누적)"
                            )
                            break  # 재시도 루프 종료하고 다음 배치로 진행
                        # 일부 또는 전체 실패 시, 실패한 항목만 재시도를 위해 준비
                        await LogManager.warning(
                            f"[UPLOAD] 배치 {current_batch_num} 부분 실패 (시도 {attempt + 1}/{max_retries}): "
                            f"{len(succeeded_docs)}/{len(documents_to_upload)} 성공. 실패한 항목 재시도..."
                        )
                        for res_item in failed_docs:
                            await LogManager.error(f"  문서 업로드 실패: id={res_item.key}, error={res_item.error_message}")
                        # 실패한 문서 목록을 다음 재시도를 위해 갱신
                        succeeded_keys = {res.key for res in succeeded_docs}
                        documents_to_upload = [doc for doc in documents_to_upload if doc['id'] not in succeeded_keys]
                    except asyncio.TimeoutError:
                        await LogManager.error(
                            f"[UPLOAD] 배치 {current_batch_num} 타임아웃 발생 (시도 {attempt + 1}/{max_retries}). 재시도 합니다..."
                        )
                    except Exception as e:
                        await LogManager.error(
                            f"[UPLOAD] 배치 {current_batch_num} 업로드 중 예외 발생 (시도 {attempt + 1}/{max_retries}): {str(e)}. 재시도 합니다..."
                        )
                    # 재시도 전 대기 (지수 백오프 + Jitter)
                    if attempt < max_retries - 1:
                        delay = (initial_delay * (2 ** attempt)) + random.uniform(0, 1)
                        await LogManager.info(f"  {delay:.2f}초 후 재시도합니다.")
                        await asyncio.sleep(delay)
                else:
                    # for 루프가 break 없이 모두 실행된 경우 (최대 재시도 횟수 초과)
                    await LogManager.error(
                        f"[UPLOAD] 배치 {current_batch_num} 최종 실패: 최대 재시도 횟수({max_retries})를 초과했습니다."
                    )                                        

    @staticmethod
    async def get_total_count(index_name: str):
        headers = {
            "api-key": AZURE_SEARCH_API_KEY,
            "Content-Type": "application/json",
        }
        params = {'api-version': AZURE_SEARCH_API_VERSION}
        url = f"{AZURE_SEARCH_ENDPOINT}/indexes/{index_name}/docs/$count"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers,params=params) as resp:
                resp.raise_for_status()  # 상태 코드 확인
                total_count = await resp.text()
                return int(total_count)

            
    @staticmethod
    async def fetch_data_in_batches(index_name,last_max_id=None):
        headers = {
            "Content-Type": "application/json",
            "api-key": AZURE_SEARCH_API_KEY,
        }
        params = {'api-version': AZURE_SEARCH_API_VERSION}
        payload = {
            "search": "*",
            "filter": f"id gt '{last_max_id}'" if last_max_id else None,
            "orderby": "id asc",
            "top": 1000
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{AZURE_SEARCH_ENDPOINT}/indexes/{index_name}/docs/search",
                json=payload,
                headers=headers,
                params=params
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
                return data["value"]

    @staticmethod
    async def fetch_all_data(index_name,ignore_embedding=False):
        total_count = await SearchService.get_total_count(index_name)  
        last_max_id = None
        all_data = []

        while len(all_data) < total_count:
            batch = await SearchService.fetch_data_in_batches(index_name, last_max_id)
            
            if not batch:  # 더 이상 데이터가 없으면 종료
                break
            
            # 결과 추가
            all_data.extend(batch)

            # 마지막 ID 업데이트
            last_max_id = batch[-1]["id"]

        if ignore_embedding:
            for item in all_data:
                item.pop("embedding_chunk",None)
                item.pop("embedding_semantic_chunk",None)

        return all_data

async def main():
    # 사용예시
    # results = await SearchService.search(CPTKR,model_code="DV22DB8890BB",ignore_embedding=True)

    # for result in results:
    #     print(result)

    import pandas as pd
    print(datetime.now())

    result = await SearchService.fetch_all_data('dev-ytb-kr-v1')

    df = pd.DataFrame(result)
    await asyncio.to_thread(df.to_excel, 'index_output.xlsx', index=False, engine='openpyxl')

if __name__ == "__main__":
    asyncio.run(main())
import asyncpg
import os
from typing import Optional, Type, List, TypeVar, Dict, Any
from dataclasses import dataclass
from datetime import date
from abc import ABC, abstractmethod
from utils.data_common import ProductCategory
import asyncio
from urllib.parse import quote
# from dotenv import load_dotenv
from utils.common import SYSTEM_LOCATION
# load_dotenv(override=True)
from utils.common import get_secret_from_key_vault

T = TypeVar('T', bound='BaseCategory')

PGDB_USERNAME = os.environ.get("PGDB_USERNAME")
PGDB_SECRET_NAME = os.getenv("PGDB_SECRET_NAME")
PG_PWD_KEY =quote(get_secret_from_key_vault(PGDB_SECRET_NAME))
PGDB_HOST = os.environ.get("PGDB_HOST")
PGDB_DBNAME = os.environ.get("PGDB_DBNAME")



class DBManager:
    def __init__(self,db_name = None):
        if db_name is not None:
            PGDB_DBNAME = db_name
        else:
            PGDB_DBNAME = os.environ.get("PGDB_CLC_DBNAME")
        self._con_str = f"postgresql://{PGDB_USERNAME}:{PG_PWD_KEY}@{PGDB_HOST}:5432/{PGDB_DBNAME}"
        self._pool: Optional[asyncpg.Pool] = None
        self.location = LocationInfo.get_location_info()

    async def __aenter__(self):
        """컨텍스트 진입 시 연결 풀 생성"""
        if self._pool is None:
            self._pool = await asyncpg.create_pool(self._con_str, min_size=1, max_size=50,timeout=30)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """컨텍스트 종료 시 연결 풀 닫기"""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def fetch(self, query: str, *args) -> List[asyncpg.Record]:
        """쿼리 결과 가져오기"""
        async with self._pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def list_categories_kr(self):
        """
        모든 레코드를 지정된 데이터 클래스에 매핑하여 반환
        :param table_name: 조회할 테이블 이름
        :param model: 매핑할 데이터 클래스
        :return: 데이터 클래스 객체 리스트
        """
        query = f"""SELECT 
                 product_category_lv1 AS category1,
                 product_category_lv2 AS category2,
                 product_category_lv3 AS category3 
                 FROM rubicon_data_product_category 
                 GROUP BY product_category_lv1,product_category_lv2,product_category_lv3 
                 ORDER BY product_category_lv1,product_category_lv2,product_category_lv3"""
        raw_data = await self.fetch(query) 
        return [(dict(record)) for record in raw_data]
    
    async def list_categories_uk(self):
        """
        모든 레코드를 지정된 데이터 클래스에 매핑하여 반환
        :param table_name: 조회할 테이블 이름
        :param model: 매핑할 데이터 클래스
        :return: 데이터 클래스 객체 리스트
        """
        query = f"""SELECT 
                 category_lv1 AS category1,
                 category_lv2 AS category2,
                 category_lv3 AS category3
                 FROM rubicon_data_uk_product_spec_basics 
                 GROUP BY category_lv1,category_lv2,category_lv3 
                 ORDER BY category_lv1,category_lv2,category_lv3"""
        raw_data = await self.fetch(query) 
        return [(dict(record)) for record in raw_data]
    
    async def valid_category(self, cate1: str, cate2: str, cate3: str) -> bool:
        """
        주어진 카테고리가 유효한지 확인합니다.
        :param cate1: 1단계 카테고리
        :param cate2: 2단계 카테고리
        :param cate3: 3단계 카테고리
        :return: True (유효) / False (무효)
        """
        query = """
            SELECT COUNT(*) AS count 
            FROM rubicon_data_product_category
            WHERE product_category_lv1 = $1 
            AND product_category_lv2 = $2 
            AND product_category_lv3 = $3
        """
        raw_data = await self.fetch(query, cate1, cate2, cate3)
        count = raw_data[0]['count'] if raw_data else 0
        return count > 0


    async def list_all(self,where_clause:Optional[str], table_name: str, model: Type[T], select_clause:str="*") -> List[ProductCategory]:
        """
        모든 레코드를 지정된 데이터 클래스에 매핑하여 반환
        :param table_name: 조회할 테이블 이름
        :param model: 매핑할 데이터 클래스
        :return: 데이터 클래스 객체 리스트
        """
        query = f"SELECT {select_clause} FROM {table_name}"
        if where_clause:
            query += f" {where_clause}"
        raw_data = await self.fetch(query) 
        return [model(**dict(record)).to_category() for record in raw_data]
    # version 관리 주석처리
    # async def get_index_name(self,data_name: str) -> str:
    #     """
    #     해당 데이터가 적재되어야할 인덱스 명을 가져옵니다.
    #     :param data_name: 데이터명
    #     :return: target_index
    #     """
    #     query = """
    #         SELECT index_name as indexname
    #         FROM pipeline_index_version_info
    #         WHERE data_name = $1 
    #     """
    #     raw_data = await self.fetch(query, data_name)
    #     result =  raw_data[0]['indexname'] if raw_data[0]['indexname'] else False
    #     return result
    
    # async def get_batch_version(self,data_name: str) -> str:
    #     """
    #     해당 데이터가 적재되어있는 최종 배치 버전을 가져옵니다.
    #     :param data_name: 데이터명
    #     :return: batch_version
    #     """
    #     query = """
    #         SELECT batch_version as batchversion
    #         FROM pipeline_index_version_info
    #         WHERE data_name = $1 
    #     """
    #     raw_data = await self.fetch(query, data_name)
    #     result =  raw_data[0]['batchversion'] if raw_data[0]['batchversion'] else False
    #     return result
    
    async def get_category(self) -> List[ProductCategory]:
        """
        특정 LocationInfo에 기반해 데이터를 조회
        :param location: LocationInfo 객체
        :return: 데이터 클래스 객체 리스트
        """
        return await self.list_all(None,self.location[0], self.location[1],self.location[1].get_field_names())
    
    async def get_category_model_name(self, model_name:str) -> List[ProductCategory]:
        """
        특정 LocationInfo에 기반해 데이터를 조회
        :param location: LocationInfo 객체
        :return: 데이터 클래스 객체 리스트
        """
        return await self.list_all(f"WHERE {self.location[2][0]} = '{model_name}'",self.location[0], self.location[1],self.location[1].get_field_names())


    async def get_category_model_code(self, model_code:str) -> List[ProductCategory]:
        """
        특정 LocationInfo에 기반해 데이터를 조회
        :param location: LocationInfo 객체
        :return: 데이터 클래스 객체 리스트
        """
        return await self.list_all(f"WHERE {self.location[2][1]} = '{model_code}'",self.location[0], self.location[1],self.location[1].get_field_names())
    
    async def get_model_code_by_uuid(self, uuid: str) -> List[Dict[str, Any]]:
        """
        주어진 UUID에 해당하는 model_code와 external_product 여부를 조회합니다.
        :param uuid: UUID 값
        :return: model_code와 external_product 여부를 포함한 리스트
        """
        query = """
            SELECT a.model_code, b.id IS NULL AS external_product
            FROM (
                SELECT catalog.model_code
                FROM rubicon_data_smartthings_catalog AS catalog
                WHERE EXISTS (
                    SELECT 1
                    FROM jsonb_array_elements(catalog.categories) AS explore_elem
                    WHERE explore_elem->>'uuid' = $1
                )
            ) a
            LEFT JOIN rubicon_data_product_category AS b
            ON a.model_code = b.mdl_code;
        """
        raw_data = await self.fetch(query, uuid)
        return [dict(record) for record in raw_data]
    
    async def update(self, query, *params) :
        """
        Update the processed status of a record in the specified table.
        """
        async with self._pool.acquire() as conn:
            await conn.execute(query, *params)

@dataclass
class BaseCategory(ABC):
    """국가별 카테고리 데이터의 공통 기반 클래스"""
    @abstractmethod
    def to_category(self) -> ProductCategory:
        """표준화된 ProductCategory로 변환 (자식 클래스에서 구현 필요)"""
        pass
    @abstractmethod
    def get_field_names(cls) -> ProductCategory:
        """필드명 추출 (자식 클래스에서 구현 필요)"""
        pass

@dataclass
class ProductCategoryKR(BaseCategory):
    id: int
    business_unit: Optional[str]
    product_category_lv1: Optional[str]
    product_category_lv2: Optional[str]
    product_category_lv3: Optional[str]
    model_name: Optional[str]
    mdl_code: Optional[str]
    goods_id: Optional[str]
    goods_nm: Optional[str]
    model_group_code: Optional[str]
    product_model: Optional[str]

    @classmethod
    def get_field_names(cls):
        return ",".join(cls.__annotations__.keys())
    
    def to_category(self) -> ProductCategory:
        return ProductCategory(
            bu=self.business_unit,
            model_code=self.mdl_code,
            model_name=self.model_name,
            category1=self.product_category_lv1,
            category2=self.product_category_lv2,
            category3=self.product_category_lv3,
            goods_id=self.goods_id,
            goods_nm=self.goods_nm
        )

@dataclass
class ProductCategoryUK(BaseCategory):
    MODEL_CODE: str
    DISPLAY: str
    SITE: str
    IS_B2C: str
    REVIEWCOUNT: Optional[int]
    IS_INSURANCE: str
    CREATION_DATE: Optional[date]
    MODEL_NAME: str
    LAUNCH_DATE: Optional[date]
    PRODUCT_DESC: str
    TOP_FLAG: str
    TOP_FLAG_PERIOD_FROM: Optional[date]
    TOP_FLAG_PERIOD_TO: Optional[date]
    DISPLAY_NAME: str
    CATEGORY_CODE1: Optional[str]
    CATEGORY_LV1: str
    CATEGORY_CODE2: Optional[str]
    CATEGORY_LV2: str
    CATEGORY_CODE3: Optional[str]
    CATEGORY_LV3: str
    PRODUCT_URL: str
    CATEGORY: Optional[str]
    CATEGORY_NAME: str

    @classmethod
    def get_field_names(cls):
        return ",".join(cls.__annotations__.keys())
    def to_category(self) -> ProductCategory:
        return ProductCategory(
            bu=None,
            model_code=self.MODEL_CODE,
            model_name=self.MODEL_NAME,
            category1=self.CATEGORY_LV1,
            category2=self.CATEGORY_LV2,
            category3=self.CATEGORY_LV3,
            goods_id=None,
            goods_nm=self.DISPLAY_NAME,
        )
    
class LocationInfo:    
    MAPPING = {
        "KR": ("rubicon_data_product_category", ProductCategoryKR, ("model_name", "mdl_code")),
        "UK": ("rubicon_data_uk_product_spec_basics", ProductCategoryUK, ("MODEL_NAME", "MODEL_CODE")),
    }

    @staticmethod
    def get_location_info():
        if SYSTEM_LOCATION not in LocationInfo.MAPPING:
            raise ValueError(f"Invalid SYSTEM_LOCATION value: {SYSTEM_LOCATION}")
        return LocationInfo.MAPPING[SYSTEM_LOCATION]


async def main():
    # 사용예시
    async with DBManager() as db_manager:
        categories_kr = await db_manager.get_category_model_code(location=LocationInfo.KR, model_code="JBLTBEAMBLKAS")
        for category in categories_kr:
            print(category)


if __name__ == "__main__":
    asyncio.run(main())
from dataclasses import dataclass, field, fields
from utils.data_cosmos import ContainerBaseModel
from utils.data_search import IndexBase
from utils.task_info import RefBaseModel
from typing import Optional,List
import os


COSMOS_SEED_CONTAINER_NAME = os.environ.get("COSMOS_SEED_CONTAINER_NAME")
COSMOS_SEARCH_CONTAINER_NAME = os.environ.get("COSMOS_SEARCH_CONTAINER_NAME")


## RefBaseModel 선언부. Cosmos에 넣어 줄 데이터를 정의 합니다
@dataclass
class PimRefData(RefBaseModel):
    title: Optional[str] = None
    chunk: Optional[str] = None
    content: Optional[str] = None
    semantic_chunk: Optional[str] = None
    blob_path: Optional[str] = None
    chunk_seq: Optional[int] = None
    semantic_chunk_seq: Optional[int] = None
    bu: Optional[str] = None
    category1: Optional[str] = None
    category2: Optional[str] = None
    category3: Optional[str] = None
    is_display: Optional[int] =None
    goods_id: List[str] = field(default_factory=list)
    goods_nm: List[str] = field(default_factory=list)
    model_code: List[str] = field(default_factory=list)
    model_name: List[str] = field(default_factory=list)

class PimSeedContainer(ContainerBaseModel):
    def __init__(self, bulk_mode = False):
        super().__init__(COSMOS_SEED_CONTAINER_NAME, bulk_mode=bulk_mode)

class PimSearchContainer(ContainerBaseModel):
    def __init__(self, bulk_mode = False):
        super().__init__(COSMOS_SEARCH_CONTAINER_NAME, bulk_mode=bulk_mode)

class PimSearch(IndexBase):
    def __init__(self, **kwargs):
        valid_field_names = {f.name for f in fields(self)}
        filtered_kwargs = {k: v for k, v in kwargs.items() if k in valid_field_names}
        super().__init__(**filtered_kwargs)
    
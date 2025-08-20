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
class MediaRefData(RefBaseModel):
    category1: Optional[str] = None
    category2: Optional[str] = None
    category3: Optional[str] = None
    title: Optional[str] = None
    blob_path: Optional[str] = None
    chunk: Optional[str] = None
    semantic_chunk: Optional[str] = None
    type: Optional[str] = None
    chunk_seq: Optional[int] = None
    display_seq: Optional[int] = None
    is_display: Optional[int] = None
    reg_date: Optional[str] = None
    disp_strt_dtm: Optional[str] = None
    disp_end_dtm: Optional[str] = None
    goods_id: List[str] = field(default_factory=list)
    goods_nm: List[str] = field(default_factory=list)
    img_data: List[str] = field(default_factory=list)
    model_code: List[str] = field(default_factory=list)
    model_name: List[str] = field(default_factory=list)

class MediaSeedContainer(ContainerBaseModel):
    def __init__(self, bulk_mode = False):
        super().__init__(COSMOS_SEED_CONTAINER_NAME, bulk_mode=bulk_mode)

class MediaSearchContainer(ContainerBaseModel):
    def __init__(self, bulk_mode = False):
        super().__init__(COSMOS_SEARCH_CONTAINER_NAME, bulk_mode=bulk_mode)

class MediaSearch(IndexBase):
    def __init__(self, **kwargs):
        valid_field_names = {f.name for f in fields(self)}
        filtered_kwargs = {k: v for k, v in kwargs.items() if k in valid_field_names}
        super().__init__(**filtered_kwargs)
    
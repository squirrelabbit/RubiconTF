from typing import Optional, Type, List, TypeVar,ClassVar, Union, Dict, Any
from dataclasses import dataclass
from datetime import date,datetime
import hashlib
import json
from dataclasses import dataclass, asdict
from typing import Optional, List, Union

@dataclass
class CommonPipelineData:
    pipe_youtube_last_exec_date: Optional[datetime] = None

@dataclass
class ProductCategory:
    bu: Optional[str] = None
    category1: Optional[str] = None
    category2: Optional[str] = None
    category3: Optional[str] = None
    model_name: Optional[Union[str, List[str]]] = None
    model_code: Optional[Union[str, List[str]]] = None
    goods_id: Optional[Union[str, List[str]]] = None
    goods_nm: Optional[Union[str, List[str]]] = None
    model_group_code: Optional[Union[str, List[str]]] = None
    product_model: Optional[Union[str, List[str]]] = None


def merge_product_categories(categories: List[ProductCategory]) -> List[ProductCategory]:
    merged_dict: Dict[tuple, ProductCategory] = {}

    for category in categories:
        key = (category.bu, category.category1, category.category2, category.category3) 

        if key not in merged_dict:
            merged_dict[key] = ProductCategory(
                bu=category.bu,
                category1=category.category1,
                category2=category.category2,
                category3=category.category3,
                model_name=set(),
                model_code=set(),
                goods_id=set(),
                goods_nm=set(),
                model_group_code=set(),
                product_model=set()
            )

        merged = merged_dict[key]

        for field in ["model_name", "model_code", "goods_id", "goods_nm",
                      "model_group_code", "product_model"]:
            value = getattr(category, field)
            if value:
                if isinstance(value, list):
                    merged_dict[key].__dict__[field].update(value)
                else:
                    merged_dict[key].__dict__[field].add(value)


    for merged in merged_dict.values():
        for field in ["model_name", "model_code", "goods_id", "goods_nm",
                      "model_group_code", "product_model"]:
            merged.__dict__[field] = list(merged.__dict__[field]) if merged.__dict__[field] else []

    return list(merged_dict.values())


def generate_id(obj) -> str:
    """
    특정 필드만 활용하여 SHA-256 해시를 생성하고, ID 값만 반환
    - 필드 순서를 유지하여 title부터 url까지 일관되게 입력값 구성
    - JSON 직렬화 시 한글 그대로 출력 (`ensure_ascii=False`)
    - None, "", "null" 값은 해싱에 영향을 주지 않음
    """
    # 사용할 필드 리스트 (순서 유지)
    fields = [
        "system_name",
        "title", "content", "answer", "blob_path", "chunk", "disclaimer",
        "file_name", "question", "question_category", "type", "img_data", "url",
        "category1", "category2", "category3", "model_code"
    ]
    # Dataclass를 딕셔너리로 변환
    obj_dict = asdict(obj)
    # 필드 값에서 무효값(None, "", "null") 제거 및 최소 변환
    filtered_data = {
        key: (",".join(obj_dict[key]) if isinstance(obj_dict[key], list) else obj_dict[key])
        for key in fields if obj_dict.get(key) not in [None, "", "null"]
    }
    # JSON을 문자열로 변환 (필드 순서 유지, 한글 그대로 출력)
    json_str = json.dumps(filtered_data, ensure_ascii=False, separators=(',', ':'))

    # SHA-256 해싱
    hash_value = hashlib.sha256(json_str.encode()).hexdigest()
    obj.id = hash_value
    return obj  # ID 값만 반환


def batch_list(data_list, batch_size):
    """Yield successive batch_size chunks from data_list along with their sizes and total batch count."""
    total_batches = (len(data_list) + batch_size - 1) // batch_size
    for i in range(0, len(data_list), batch_size):
        batch = data_list[i:i + batch_size]
        yield batch, total_batches
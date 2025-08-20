import re
import json
import hashlib
from dataclasses import dataclass
from urllib.parse import urljoin
from dataclasses import dataclass, field
from typing import Optional,List
from src.modules.embedding import embedding_text

@dataclass
class InferenceData:
    """
    AI 기반 캡션 생성을 위한 입력 데이터를 구조화
    """
    caption: str
    url: str
    category1: str
    category2: str
    category3: str
    chunk: str
    goods_nm: str
    ocr: str
    

@dataclass
class IndexBase:    
    def __init__(self, row, bu=None, chunk_seq=0, chunk="", semantic_chunk_seq=0, semantic_chunk="", content =""):
        self.row = row
        self.bu = bu
        self.chunk_seq = int(chunk_seq)
        self.chunk = str(chunk)
        self.model_code = self.row.get("model_code", "")
        self.model_name = self.row.get("model_name", "")
        self.display_name = self.row.get("display_name", "")
        self.category1 = self.row.get("category1", "")
        self.category2 = self.row.get("category2", "")
        self.category3 = self.row.get("category3", "")
        self.blob_path = urljoin("https://www.samsung.com", self.row.get("product_url"))
        self.semantic_chunk_seq = int(semantic_chunk_seq)
        self.semantic_chunk = semantic_chunk
        self.content = content

    def to_upload_sch_data(self):
        return {
            # "id": id,
            "chunk_seq": self.chunk_seq,
            "semantic_chunk_seq": self.semantic_chunk_seq,
            "title": self.display_name,
            "bu": self.bu,
            "category1": self.category1,
            "category2": self.category2,
            "category3": self.category3,            
            "goods_nm": [self.display_name],
            "model_name": [self.model_name],
            "model_code": [self.model_code],
            "goods_id": [self.model_code],
            "blob_path": self.blob_path,
            "chunk": self.chunk,
            "semantic_chunk": self.semantic_chunk,
            "is_display": 1,
            # "embedding_chunk": embedding_text(self.chunk),
            # "embedding_semantic_chunk": embedding_text(self.semantic_chunk)
        }
    
    
    def to_inference_data(self, src, old_alt="", ocr="", chunk=""):
        """InferenceData 객체 생성"""
        return InferenceData(
            caption=old_alt,
            url=src,
            category1=self.category1,
            category2=self.category2,
            category3=self.category3,
            chunk=chunk,
            goods_nm=self.display_name,
            ocr=ocr
        )

def custom_generate_id(data: dict) -> str:
    """
    특정 필드만 활용하여 SHA-256 해시를 생성하고, ID 값만 반환
    - 필드 순서를 유지하여 title부터 url까지 일관되게 입력값 구성
    - JSON 직렬화 시 한글 그대로 출력 (`ensure_ascii=False`)
    - None, "", "null" 값은 해싱에 영향을 주지 않음
    """
    # 사용할 필드 리스트 (순서 유지)
    fields = [
        "system_name",
        "title", "content", "answer", "blob_path", "chunk","semantic_chunk", "disclaimer",
        "file_name", "question", "question_category", "type", "img_data", "url",
        "category1", "category2", "category3", "model_code", "chunk_seq", "semantic_chunk_seq"
    ]
    # Dataclass를 딕셔너리로 변환
    # 필드 값에서 무효값(None, "", "null") 제거 및 최소 변환
    filtered_data = {
        key: (",".join(data[key]) if isinstance(data[key], list) else data[key])
        for key in fields if data.get(key) not in [None, "", "null"]
    }
    # JSON을 문자열로 변환 (필드 순서 유지, 한글 그대로 출력)
    json_str = json.dumps(filtered_data, ensure_ascii=False, separators=(',', ':'))

    # SHA-256 해싱
    hash_value = hashlib.sha256(json_str.encode()).hexdigest()
    return f"{hash_value}"


def generate_filter_id(obj:dict) -> str:
    """
    특정 필드만 활용하여 SHA-256 해시를 생성하고, ID 값만 반환
    - 필드 순서를 유지하여 title부터 url까지 일관되게 입력값 구성
    - JSON 직렬화 시 한글 그대로 출력 (`ensure_ascii=False`)
    - None, "", "null" 값은 해싱에 영향을 주지 않음
    """
    # 사용할 필드 리스트 (순서 유지)
    fields = [
        "model_code",
    ]
    # Dataclass를 딕셔너리로 변환
    # 필드 값에서 무효값(None, "", "null") 제거 및 최소 변환
    filtered_data = {
        key: (",".join(obj[key]) if isinstance(obj[key], list) else obj[key])
        for key in fields if obj.get(key) not in [None, "", "null"]
    }
    # JSON을 문자열로 변환 (필드 순서 유지, 한글 그대로 출력)
    json_str = json.dumps(filtered_data, ensure_ascii=False, separators=(',', ':'))

    # SHA-256 해싱
    hash_value = hashlib.sha256(json_str.encode()).hexdigest()
    return hash_value  # ID 값만 반환
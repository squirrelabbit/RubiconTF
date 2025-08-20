import json
import hashlib
from dataclasses import asdict
from utils.data_search import IndexBase

def generate_id(obj:IndexBase) -> IndexBase:
    """
    특정 필드만 활용하여 SHA-256 해시를 생성하고, ID 값만 반환
    - 필드 순서를 유지하여 title부터 url까지 일관되게 입력값 구성
    - JSON 직렬화 시 한글 그대로 출력 (`ensure_ascii=False`)
    - None, "", "null" 값은 해싱에 영향을 주지 않음
    """
    # 사용할 필드 리스트 (순서 유지)
    fields = [
        "system_name",
        "version", "chunk_seq", 
        "blob_path", "chunk", "content",
        "category1", "category2", "category3"
    ]
    # Dataclass를 딕셔너리로 변환
    obj_dict = asdict(obj)
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

def generate_original_id(obj:IndexBase) -> IndexBase:
    """
    특정 필드만 활용하여 SHA-256 해시를 생성하고, ID 값만 반환
    - 필드 순서를 유지하여 title부터 url까지 일관되게 입력값 구성
    - JSON 직렬화 시 한글 그대로 출력 (`ensure_ascii=False`)
    - None, "", "null" 값은 해싱에 영향을 주지 않음
    """
    # 사용할 필드 리스트 (순서 유지)
    fields = [
        "system_name", "chunk_seq",
        "blob_path", "chunk", "content",
        "category1", "category2", "category3"
    ]
    # Dataclass를 딕셔너리로 변환
    obj_dict = asdict(obj)
    filtered_data = {
        key: (",".join(obj_dict[key]) if isinstance(obj_dict[key], list) else obj_dict[key])
        for key in fields if obj_dict.get(key) not in [None, "", "null"]
    }
    # JSON을 문자열로 변환 (필드 순서 유지, 한글 그대로 출력)
    json_str = json.dumps(filtered_data, ensure_ascii=False, separators=(',', ':'))
    # SHA-256 해싱
    hash_value = hashlib.sha256(json_str.encode()).hexdigest()
    obj.original_id = hash_value
    return obj  # ID 값만 반환

def generate_filter_id(obj:IndexBase) -> IndexBase:
    """
    특정 필드만 활용하여 SHA-256 해시를 생성하고, ID 값만 반환
    - 필드 순서를 유지하여 title부터 url까지 일관되게 입력값 구성
    - JSON 직렬화 시 한글 그대로 출력 (`ensure_ascii=False`)
    - None, "", "null" 값은 해싱에 영향을 주지 않음
    """
    # 사용할 필드 리스트 (순서 유지)
    fields = [
        "blob_path", "category1", "category2"
    ]
    # Dataclass를 딕셔너리로 변환
    obj_dict = asdict(obj)
    filtered_data = {
        key: (",".join(obj_dict[key]) if isinstance(obj_dict[key], list) else obj_dict[key])
        for key in fields if obj_dict.get(key) not in [None, "", "null"]
    }
    # JSON을 문자열로 변환 (필드 순서 유지, 한글 그대로 출력)
    json_str = json.dumps(filtered_data, ensure_ascii=False, separators=(',', ':'))
    # SHA-256 해싱
    hash_value = hashlib.sha256(json_str.encode()).hexdigest()
    obj.filter_id = hash_value
    return obj  # ID 값만 반환
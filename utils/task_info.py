import os
from typing import Type, TypeVar
from datetime import datetime
import uuid
from enum import Enum
import os
import base64
from dataclasses import dataclass
# from dotenv import load_dotenv
# from utils.common import SYSTEM_LOCATION
# load_dotenv(override=True)


class DBStatus(Enum):
    WAITING = 0
    COMPLETED = 1
    ERROR = 2

## Task의 상태를 정의 합니다. 
class TaskStatus(str, Enum):
    WAITING = "WAITING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"

## Task Type을 정의 합니다. 새로운 타입이 발생하면 추가 하세요.
class TaskType(str, Enum):
    DEFAULT = "DEFAULT"
    DELETE = "DELETE"
    UPDATE = "UPDATE"
    MDINSERT = "MDINSERT"
    READ_EXCEL = "READ_EXCEL"
    READ_EXCEL_WITH_SEARCH = "READ_EXCEL_WITH_SEARCH"
    READ_CSV = "READ_CSV"
    READ_DB = "READ_DB"
    BACKUP_INDEX = "BACKUP_INDEX"
    CREATE = "CREATE"


## 국가코드이며 새로운 국가 확장 시 추가 필요 합니다
class Location(str, Enum):
    KR = "KR"
    UK = "UK"

    
ItemT = TypeVar("ItemT", bound="ItemBaseModel")

class ItemBaseModel:
    id: str
    create_time: datetime
    update_time: datetime

    def __init__(self, **data):
        self.create_time = data.get('create_time', datetime.now().isoformat())
        self.update_time = data.get('update_time', datetime.now().isoformat())
        

    @staticmethod
    def generate_id() -> str:
        """
        Generate a unique ID.
        """
        return str(uuid.uuid4())

    @staticmethod
    def text_to_base64(text):
        bytes_data = text.encode('utf-8')
        base64_encoded = base64.b64encode(bytes_data)
        base64_text = base64_encoded.decode('utf-8')

        return base64_text

    def to_dict(self) -> dict:
        """
        Convert the item to a dictionary for Cosmos DB storage.
        """
        item_dict = {}
        for k, v in self.__dict__.items():
            if callable(v) or isinstance(v, type):  # 함수나 클래스 제외
                continue
            if isinstance(v, RefBaseModel):  # ref_data가 클래스 객체일 경우
                item_dict[k] = v.to_dict()
            if hasattr(v, "to_dict"):
                item_dict[k] = v.to_dict()
            elif isinstance(v, Enum):  
                item_dict[k] = v.value
            elif isinstance(v, datetime):  
                item_dict[k] = v.isoformat()
            else:
                item_dict[k] = v
        return item_dict


    def from_dict(self: Type[ItemT], data: dict) -> ItemT:
        """
        Create an instance of the item from a dictionary.
        """
        return self(**data)

from utils.data_cosmos import ContainerBaseModel

## Cosmos DB Trigger의 기본 구조입니다. Cosmos DB는 업데이트시 매번 trigger가 발생할 수 있기에 next_action 관리 필요 (최초 입력시 True)
class SeedData(ItemBaseModel):    
    def __init__(self, **data):
        super().__init__(**data)  
        self.id = data.get('id',self.generate_id())
        self.system_name = data.get('system_name', '')
        self.version = data.get('version','')  # Search Index Version   
        self.task_type = data.get('task_type', TaskType.DEFAULT)
        self.status = data.get('status',TaskStatus.WAITING)
        self.next_action = data.get('next_action',True)
        self.ref_batch = data.get('ref_batch','')
        self.ref_num = data.get('ref_num','')
        self.ref_data = data.get('ref_data', None) 
        self.ref_source = data.get('ref_source', None)
        self.qset_flag = data.get('qset_flag', False) 

RefT = TypeVar("RefT", bound="RefBaseModel")

@dataclass
class RefBaseModel:
    def to_dict(self) -> dict:
        item_dict = self.__dict__.copy()
        return item_dict

    def from_dict(self: Type[RefT], data: dict) -> RefT:
        return self(**data)
    
from azure.cosmos import CosmosClient, ContainerProxy, PartitionKey, exceptions
from azure.cosmos.aio import CosmosClient as AsyncCosmosClient
from typing import Optional, List
import os
# from dotenv import load_dotenv

from datetime import datetime
from utils.common import get_secret_from_key_vault

# load_dotenv(override=True)

COSMOS_ENDPOINT = os.environ.get("COSMOS_ENDPOINT")
COSMOS_DB_SECRET_NAME = os.environ.get("COSMOS_DB_SECRET_NAME")
COSMOS_KEY = get_secret_from_key_vault(COSMOS_DB_SECRET_NAME)
COSMOS_DB_NAME = os.environ.get("COSMOS_DB_NAME")

class ContainerBaseModel:
    def __init__(self, container_name: str, bulk_mode: bool = False):
        if bulk_mode:
            self.client = AsyncCosmosClient(
                COSMOS_ENDPOINT,
                COSMOS_KEY,
                consistency_level="Eventual",
                connection_config={"bulk": True}
            )
        else:
            self.client = AsyncCosmosClient(
                COSMOS_ENDPOINT,
                COSMOS_KEY
            )
        self.database_name = COSMOS_DB_NAME
        self.container_name = container_name

        self.container = None

    async def _initialize_container(self):
        """
        Initialize container if it doesn't exist.
        """
        database = self.client.get_database_client(self.database_name)
        try:
            self.container = await database.create_container_if_not_exists(
                id=self.container_name,
                partition_key=PartitionKey(path="/id")
            )
        except exceptions.CosmosHttpResponseError as e:
            print(f"Error initializing container: {e}")
            raise

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        await self.client.close()  # Ensure client is closed properly

    async def get_container(self) -> ContainerProxy:
        if not self.container:
            await self._initialize_container()
        return self.container

    async def find(self, filters: Optional[dict] = None, select_fields: Optional[List[str]] = None) -> List[dict]:
        """
        Find items from Cosmos DB based on dynamic filters and selectable fields.
        """
        container = await self.get_container()
        select_clause = "SELECT *" if not select_fields else "SELECT " + ", ".join([f"c.{field}" for field in select_fields])

        query = f"{select_clause} FROM c"  # Base query

        if filters:
            conditions = [f"c.{key} = @{key}" for key in filters.keys()]
            query += " WHERE " + " AND ".join(conditions)

        parameters = [{"name": f"@{key}", "value": value} for key, value in filters.items()] if filters else []

        return [
            item async for item in container.query_items(query=query, parameters=parameters)
        ]

    async def delete(self, item_id: str, partition_key: str) -> None:
        """
        Delete an item from Cosmos DB by ID.
        """
        container = await self.get_container()
        await container.delete_item(item_id, partition_key=partition_key)

    async def bulk_insert(self, items) -> None:
        """
        Insert multiple items into the Cosmos DB container.
        """
        container = await self.get_container()

        for item in items:
            if hasattr(item, "to_dict"):
                body = item.to_dict()
            else:
                body = item
            await container.create_item(body=body)

    async def upsert(self, item) -> None:
        """
        Upsert a single item into the Cosmos DB container.
        """
        container = await self.get_container()
        if hasattr(item, "to_dict"):
            body = item.to_dict()
        else:
            body = item

        await container.upsert_item(body=body)
            
    async def insert(self, item) -> None:
        """
        Insert a single item into the Cosmos DB container.
        """
        container = await self.get_container()
        if hasattr(item, "to_dict"):
            body = item.to_dict()
        else:
            body = item

        await container.create_item(body=body)


import uuid
from enum import Enum

class WorkerLogContainer(ContainerBaseModel):
    async def save_log(self,system_name,status,task_type):
        await self.upsert(
            item = dict(
                id = str(uuid.uuid4()),
                system_name = system_name,
                status = status,
                task_type = task_type,
                log_date = datetime.now().isoformat()
            )
        )
    def __init__(self, bulk_mode = False):
        super().__init__("cont_worker_log", bulk_mode=bulk_mode)

class LogContainer(ContainerBaseModel):
    def __init__(self, bulk_mode = False):
        super().__init__("cont_log", bulk_mode=bulk_mode)

class ErrorLogContainer(ContainerBaseModel):
    def __init__(self, bulk_mode = False):
        super().__init__("cont_errorlog", bulk_mode=bulk_mode)


# 각 컨테이너는 개별 모듈에서 상속 받아서 사용. 컨테이너명은 겹치지 않도록 한다

# class SeedContainer(ContainerBaseModel):
#     def __init__(self, bulk_mode = False):
#         super().__init__("cont_seed", bulk_mode=bulk_mode)

# class CommonContainer(ContainerBaseModel):
#     def __init__(self, bulk_mode = False):
#         super().__init__("cont_common", bulk_mode=bulk_mode)

# class ScheduleContainer(ContainerBaseModel):
#     def __init__(self, bulk_mode = False):
#         super().__init__("cont_schedule", bulk_mode=bulk_mode)

# class SMTCategoriesContainer(ContainerBaseModel):
#     def __init__(self, bulk_mode = False):
#         super().__init__("cont_smtcate", bulk_mode=bulk_mode)
import os
from azure.storage.blob.aio import BlobServiceClient
from azure.storage.blob import ContentSettings
# 제공된 AzureBlobStorageAsync 클래스
class AzureBlobStorageAsync:
    def __init__(self, connection_string):
        self.connection_string = connection_string
    async def list_blobs(self, container_name):
        blob_service_client = BlobServiceClient.from_connection_string(self.connection_string)
        try:
            container_client = blob_service_client.get_container_client(container_name)
            blob_list = []
            async for blob in container_client.list_blobs():
                blob_list.append(blob.name)
            return blob_list
        finally:
            await blob_service_client.close()
    async def download_blob(self, container_name, blob_name):
        blob_service_client = BlobServiceClient.from_connection_string(self.connection_string)
        try:
            blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
            download_stream = await blob_client.download_blob()
            return await download_stream.readall()
        finally:
            await blob_service_client.close()
    async def upload_blob(self, container_name, blob_name, data, content_type='image/png'):
        blob_service_client = BlobServiceClient.from_connection_string(self.connection_string)
        try:
            blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
            await blob_client.upload_blob(
                data=data,
                overwrite=True,
                content_settings=ContentSettings(content_type=content_type)
            )
        finally:
            await blob_service_client.close()
# 예제: 특정 컨테이너의 파일 목록을 확인하고, 각 파일을 다운로드하여 로컬 디렉토리에 저장
async def list_and_download_blobs(connection_string: str, container_name: str, download_dir: str):
    storage = AzureBlobStorageAsync(connection_string)
    # 컨테이너 내 blob 목록 가져오기
    blob_list = await storage.list_blobs(container_name)
    print("Blobs found:", blob_list)
    # 다운로드 폴더가 없으면 생성
    os.makedirs(download_dir, exist_ok=True)
    for blob_name in blob_list:
        # 각 blob 다운로드
        data = await storage.download_blob(container_name, blob_name)
        # 파일 경로 설정 (blob 이름 그대로 사용)
        file_path = os.path.join(download_dir, blob_name)
        # 하위 디렉토리가 있을 경우 생성
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'wb') as f:
            f.write(data)
        print(f"Downloaded '{blob_name}' to '{file_path}'")
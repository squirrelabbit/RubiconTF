from azure.storage.blob.aio import BlobServiceClient
from azure.storage.blob import ContentSettings
from azure.identity import ManagedIdentityCredential
import os

CREDENTIAL_CLIENT_ID = os.environ.get('CREDENTIAL_CLIENT_ID')

class AzureBlobStorageAsync:
    def __init__(self, account_url):
        self.account_url = account_url
        self.credential = ManagedIdentityCredential(client_id=CREDENTIAL_CLIENT_ID)

    async def list_blobs(self, container_name):
        blob_service_client = BlobServiceClient(account_url=self.account_url, credential=self.credential)
        try:
            container_client = blob_service_client.get_container_client(container_name)
            blob_list = []
            async for blob in container_client.list_blobs():
                blob_list.append(blob.name)
            return blob_list
        finally:
            await blob_service_client.close()

    async def download_blob(self, container_name, blob_name):
        blob_service_client = BlobServiceClient(account_url=self.account_url, credential=self.credential)
        try:
            blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
            download_stream = await blob_client.download_blob()
            return await download_stream.readall()
        finally:
            await blob_service_client.close()

    async def upload_blob(self, container_name, blob_name, data, content_type='image/png'):
        blob_service_client = BlobServiceClient(account_url=self.account_url, credential=self.credential)
        try:
            blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
            await blob_client.upload_blob(
                data=data,
                overwrite=True,
                content_settings=ContentSettings(content_type=content_type)
            )
        finally:
            await blob_service_client.close()
            
    async def blob_exists(self, container_name, blob_name):
        blob_service_client = BlobServiceClient(account_url=self.account_url, credential=self.credential)
        try:
            blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
            return await blob_client.exists()
        finally:
            await blob_service_client.close()
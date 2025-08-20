import os
from dotenv import load_dotenv
load_dotenv(override=True)

from azure.identity import ManagedIdentityCredential
from azure.keyvault.secrets import SecretClient

SYSTEM_LOCATION = os.environ.get("SYSTEM_LOCATION")
KEY_VAULT_URL = os.environ.get('KEY_VAULT_URL')
CREDENTIAL_CLIENT_ID = os.environ.get('CREDENTIAL_CLIENT_ID')


def get_secret_from_key_vault(secret_name: str) -> str:
    """
    Azure Key Vault에서 지정된 이름의 비밀을 가져옵니다.
    """
    credential = ManagedIdentityCredential(client_id=CREDENTIAL_CLIENT_ID)
    key_vault_client = SecretClient(vault_url=KEY_VAULT_URL, credential=credential)
    return key_vault_client.get_secret(secret_name).value
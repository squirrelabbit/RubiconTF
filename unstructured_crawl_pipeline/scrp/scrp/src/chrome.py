import os
import subprocess
import re
import zipfile 
import asyncio
from utils.data_blob import AzureBlobStorageAsync

TEMP_DIR = "/tmp/chrome_install"
CHROME_DEB_PATH = f"{TEMP_DIR}/google-chrome-stable_current_amd64.deb"
CHROMEDRIVER_ZIP_PATH = f"{TEMP_DIR}/chromedriver-linux64.zip"
EXTRACT_DIR = "/usr/local/bin"

BLOB_ACCOUNT_URL = os.environ.get('BLOB_ACCOUNT_URL')
BLOB_CONTAINER_NAME = os.environ.get('BLOB_CONTAINER_NAME')

def run_command(command):
    subprocess.run(command, shell=True, check=True)
      
def install_latest_chrome():
    run_command(f"apt install -y {CHROME_DEB_PATH}")
    print("최신 Chrome 설치 완료")
    
def install_latest_chromedriver():
    with zipfile.ZipFile(CHROMEDRIVER_ZIP_PATH, 'r') as zip_ref:
        zip_ref.extractall(EXTRACT_DIR)
    print(f"파일 압축 해제 완료: {EXTRACT_DIR}")
    # 실행 권한 부여 및 chromedriver 이동
    run_command(f"chmod +x {EXTRACT_DIR}/chromedriver-linux64/chromedriver")
    run_command(f"mv {EXTRACT_DIR}/chromedriver-linux64/chromedriver /usr/local/bin/chromedriver")
    print("ChromeDriver 설치 완료")

async def install_chrome():
    await list_and_download_blobs(TEMP_DIR)
    
    install_latest_chrome()
    install_latest_chromedriver()
    print("모든 과정이 완료됨")

async def list_and_download_blobs(download_dir: str):
    storage = AzureBlobStorageAsync(account_url=BLOB_ACCOUNT_URL)
    # 컨테이너 내 blob 목록 가져오기
    blob_list = await storage.list_blobs(BLOB_CONTAINER_NAME)
    print("Blobs found:", blob_list)
    # 다운로드 폴더가 없으면 생성
    os.makedirs(download_dir, exist_ok=True)
    for blob_name in blob_list:
        # 각 blob 다운로드
        data = await storage.download_blob(BLOB_CONTAINER_NAME, blob_name)
        # 파일 경로 설정 (blob 이름 그대로 사용)
        file_path = os.path.join(download_dir, blob_name)
        # 하위 디렉토리가 있을 경우 생성
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'wb') as f:
            f.write(data)
        print(f"Downloaded '{blob_name}' to '{file_path}'")

if __name__ == "__main__":
    asyncio.run(install_chrome())
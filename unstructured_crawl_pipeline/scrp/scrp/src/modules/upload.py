import os
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential
from azure.search.documents.indexes import SearchIndexClient
import json
from src.config.settings import AZURE_SEARCH, AZURE_IMG_SEARCH
from tqdm import tqdm
from dotenv import load_dotenv

load_dotenv(override=True)

# 검색 클라이언트 설정
credential = AzureKeyCredential(AZURE_SEARCH["api_key"])
search_client = SearchClient(
    endpoint=AZURE_SEARCH["endpoint"], 
    index_name=AZURE_SEARCH["index_name"], 
    credential=credential)


# 로컬 JSON 파일 읽기
def upload_json_to_search_index(json_file_path):
    with open(json_file_path, "r", encoding="utf-8") as file:
        documents = json.load(file)
        
        # 파일이 배열 형태가 아닌 경우, 배열로 감싸기
        if not isinstance(documents, list):
            documents = [documents]  # 하나의 문서라도 배열로 감쌈

    try:
        search_client.upload_documents(documents=documents)
        print("Documents uploaded successfully.")
    except Exception as e:
        print(f"Error uploading documents: {e}")

def upload_from_file(folder_path):
    total_uploaded = 0  # 업로드 성공 카운트
    total_failed = 0    # 업로드 실패 카운트
    total_duplicates = 0  # 중복 문서 카운트
    total_merged = 0     # 덮어쓰기(merge) 카운트

    def is_id_duplicate(doc_id):
        try:
            result = search_client.get_document(key=doc_id)
            return True if result else False
        except Exception:
            return False

    # JSON 파일 처리
    json_files = [f for f in os.listdir(folder_path) if f.endswith(".json")]
    for filename in tqdm(json_files, desc="Processing JSON Files", unit="file"):
        json_file_path = os.path.join(folder_path, filename)
        try:
            with open(json_file_path, "r", encoding="utf-8") as file:
                documents = json.load(file)
                if not isinstance(documents, list):
                    documents = [documents]  # 단일 문서도 리스트로 변환

                duplicate_ids = []
                valid_documents = []
                failed_documents = []

                # 문서 중복 및 유효성 검사
                for doc in documents:
                    if "id" in doc:  # 문서 ID 필드 확인
                        if is_id_duplicate(doc["id"]):
                            duplicate_ids.append(doc)
                        else:
                            valid_documents.append(doc)
                    else:
                        print(f"Document in {filename} is missing an 'id' field.")

                # 유효한 문서 업로드
                if valid_documents:
                    response = search_client.upload_documents(documents=valid_documents)
                    for res, doc in zip(response, valid_documents):
                        if res.succeeded:
                            total_uploaded += 1
                        else:
                            print(f"Failed to upload document with ID {doc['id']}: {res.error_message}")
                            failed_documents.append(doc["id"])
                            total_failed += 1

                # 중복된 문서 병합 처리
                if duplicate_ids:
                    print(f"Duplicate documents in {filename}: {[doc['id'] for doc in duplicate_ids]}")

                    response = search_client.merge_or_upload_documents(documents=duplicate_ids)
                    for res, doc in zip(response, duplicate_ids):
                        if res.succeeded:
                            total_merged += 1
                        else:
                            print(f"Failed to merge-upload document with ID {doc['id']}: {res.error_message}")
                            failed_documents.append(doc["id"])
                            total_failed += 1

                total_duplicates += len(duplicate_ids)

        except Exception as e:
            print(f"Error processing file {filename}: {e}")

    # 전체 요약 출력
    print("\n=== Upload Summary ===")
    print(f"Total Documents Uploaded: {total_uploaded}")
    print(f"Total Merge-Uploaded: {total_merged}")
    print(f"Total Upload Failures: {total_failed}")
    print(f"Total Duplicates Skipped: {total_duplicates}")
    print("======================")


def delete_all_documents():
    try:
        # 1. 모든 문서 검색 (select 필드에 id를 포함해야 함)
        results = search_client.search(search_text="*", select=["id"])
        doc_ids = [doc["id"] for doc in results]

        # 2. 문서 삭제
        if doc_ids:
            # ID 리스트를 사용하여 문서 삭제
            response = search_client.delete_documents(documents=[{"id": doc_id} for doc_id in doc_ids])
            print(f"{doc_ids} documents deleted successfully.")
        else:
            print("No documents found to delete.")
    except Exception as e:
        print(f"Error deleting documents: {e}")
import os
import json

def delete_documents_from_folder(folder_path):
    if not os.path.exists(folder_path):
        print(f"Folder '{folder_path}' does not exist.")
        return

    json_files = [f for f in os.listdir(folder_path) if f.endswith('.json')]
    if not json_files:
        print(f"No JSON files found in folder '{folder_path}'.")
        return

    total_deleted = 0
    total_failed = 0

    for json_file in json_files:
        file_path = os.path.join(folder_path, json_file)
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                data = json.load(file)

                # Assuming the JSON contains a list of documents or a single document
                documents = data if isinstance(data, list) else [data]

                for doc in documents:
                    doc_id = doc.get('id')
                    if doc_id:
                        print(f"Attempting to delete document with ID: {doc_id}")
                        try:
                            delete_document(doc_id)
                            total_deleted += 1
                        except Exception as e:
                            print(f"Failed to delete document with ID {doc_id}: {e}")
                            total_failed += 1
                    else:
                        print(f"No 'id' found in document in file '{json_file}'.")
                        total_failed += 1

        except Exception as e:
            print(f"Error processing file '{json_file}': {e}")
            total_failed += 1

    print(f"Deletion complete: {total_deleted} succeeded, {total_failed} failed.")


def delete_document(doc_id):
    if not doc_id:
        print("No document ID provided for deletion.")
        return

    try:
        # 단일 문서 삭제 요청
        response = search_client.delete_documents(documents=[{"id": doc_id}])

        # 삭제 성공 여부 확인
        if all(res.succeeded for res in response):
            print(f"Document with ID '{doc_id}' deleted successfully.")
        else:
            failed_docs = [res.key for res in response if not res.succeeded]
            print(f"Failed to delete document with ID: {failed_docs[0] if failed_docs else 'Unknown'}")

    except Exception as e:
        print(f"Error occurred while deleting document with ID '{doc_id}': {e}")

def get_search_count(show=False, filter_query=None):
    # Perform the search
    result = search_client.search(search_text="*", filter=filter_query, include_total_count=True)  # '*' searches all documents

    # Print the total result count
    total_count = result.get_count()
    print(f"Total results: {total_count}")

    if total_count > 0 and show:
        # Iterate through the results and display up to 10 documents
        for idx, doc in enumerate(result):
            if idx >= 10:  # Show only the first 10 results
                break
            print(f"    id: {doc.get('id')}")
            print(f"    title: {doc.get('url')}")
            print(f"    chunk: {doc.get('new_caption')}")
            # Uncomment this if you want to include image data
            # print(f"    img_data: {doc.get('img_data')}")


def upload_image(file_path):
    import os
    from azure.storage.blob import BlobServiceClient
    from src.config.settings import BLOB_SAS_ENDPOINT,BLOB_SAS_TOKEN, BLOB_SAS_IMAGE_ENDPOINT

    try:
        # BlobServiceClient 생성 (SAS URL을 사용하여 인증)
        blob_service_client = BlobServiceClient(account_url=f"{BLOB_SAS_ENDPOINT}", credential=BLOB_SAS_TOKEN)
        container_client = blob_service_client.get_container_client(BLOB_SAS_IMAGE_ENDPOINT)
        
        # 업로드할 파일 이름 추출 (Blob 이름으로 사용)
        blob_name = os.path.basename(file_path)
        
        # Blob 클라이언트 생성
        blob_client = container_client.get_blob_client(blob_name)
        
        # 파일을 바이너리 모드로 열고 업로드
        with open(file_path, "rb") as data:
            blob_client.upload_blob(data, overwrite=True)
        
          # 업로드된 Blob의 URL 생성
        blob_url = f"{BLOB_SAS_ENDPOINT}/{BLOB_SAS_IMAGE_ENDPOINT}/{blob_name}"
        print(f"업로드 성공: {file_path} -> Blob URL: {blob_url}")
        
        return blob_url

    except Exception as e:
        print(f"업로드 실패: {file_path}. 에러: {e}")
        return None

def get_index():
    index_client = SearchIndexClient(endpoint=AZURE_SEARCH["endpoint"], credential=credential)
    index = index_client.get_index(AZURE_SEARCH["index_name"])
    # 필드 설정 확인
    for field in index.fields:
        print("-----------------------------")
        print(f"Field Name: {field.name}")
        print(f"Type: {field.type}")  # 필드 타입 출력

def compare(folder):
    processed_files = 0          # 처리한 파일 수
    match_count = 0              # MATCH 카운트
    mismatch_count = 0           # MISMATCH 카운트
    no_result_count = 0          # NO RESULT 카운트

    # 폴더 내 JSON 파일 목록 가져오기
    files = [f for f in os.listdir(folder) if f.endswith('.json')]
    
    for file_name in files:  # 상위 10개 파일만 처리
        file_path = os.path.join(folder, file_name)

        # JSON 파일 열기
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                data = json.load(file)
                goods_id = data.get("goods_id", None)
                json_model_name = data.get("model_name", None)
            
            if not goods_id or not json_model_name:
                print(f"Skipping file {file_name}: Missing goods_id or model_name.")
                continue

            # Azure Search에서 goods_id로 검색
            search_filter = f"goods_id eq '{goods_id}'"
            search_result = search_client.search(search_text="", filter=search_filter)
            
            # 결과 처리
            for result in search_result:
                azure_model_name = result.get("model_name", None)
                
                # 비교 및 출력
                if azure_model_name == json_model_name:
                    # print(f"[MATCH] File: {file_name} | Goods ID: {goods_id} | Model Name: {json_model_name}")
                    match_count += 1
                else:
                    print(f"[MISMATCH] File: {file_name} | Goods ID: {goods_id} | JSON Model: {json_model_name} | Azure Model: {azure_model_name}")
                    mismatch_count += 1
                break  # 첫 번째 결과만 비교
            else:
                print(f"[NO RESULT] File: {file_name} | Goods ID: {goods_id}")
                no_result_count += 1
        except Exception as e:
            print(f"Error processing file {file_name}: {e}")
        
        processed_files += 1
    
    total_compared = match_count + mismatch_count
    match_percentage = (match_count / total_compared * 100) if total_compared > 0 else 0
    mismatch_percentage = (mismatch_count / total_compared * 100) if total_compared > 0 else 0

    print("\n=== Comparison Results ===")
    print(f"Total Processed Files: {processed_files}")
    print(f"Total Compared: {total_compared}")
    print(f"Matches: {match_count} ({match_percentage:.2f}%)")
    print(f"Mismatches: {mismatch_count} ({mismatch_percentage:.2f}%)")
    print(f"No Results: {no_result_count}")
    print("==========================")
    

def check_unique_ids(folder_path):
    id_set = set()
    duplicate_ids = []
    # 폴더 내 모든 JSON 파일 순회
    for filename in os.listdir(folder_path):
        if filename.endswith(".json"):
            file_path = os.path.join(folder_path, filename)
            with open(file_path, 'r', encoding='utf-8') as file:
                try:
                    data = json.load(file)
                    # id가 존재하고, 중복되었는지 확인
                    if 'id' in data:
                        if data['id'] in id_set:
                            duplicate_ids.append((filename, data['id']))
                        else:
                            id_set.add(data['id'])
                    else:
                        print(f"'{filename}' 파일에 'id' 필드가 없습니다.")
                except json.JSONDecodeError:
                    print(f"'{filename}' 파일은 유효한 JSON 형식이 아닙니다.")
    if duplicate_ids:
        print("중복된 ID가 발견되었습니다:")
        for file, dup_id in duplicate_ids:
            print(f"파일: {file}, 중복 ID: {dup_id}")
    else:
        print("모든 JSON 파일의 'id'가 유니크합니다.")

def update_field():
    results = search_client.search(
    search_text="*",  # 모든 문서 가져오기 (필터 있으면 추가)
    select=["id","category3", "goods_nm"]  # 조합에 필요한 필드만 가져오기
    )
    # 업데이트할 문서 리스트
    documents_to_update = []
    for result in results:
        id_value = result.get("id", "")
        category3_value = result["category3"]
        goods_nm_value = result.get("goods_nm", "")
        # 필드 조합
        new_field_value = f"{category3_value} {goods_nm_value[0]}"
        # 업데이트할 문서 생성
        doc = {
            "id": id_value,
            "semantic_keyword": new_field_value  # 새로 만들 필드
        }
        documents_to_update.append(doc)
    # 업데이트 실행 (MERGE 방식)
    if documents_to_update:
        batch = search_client.merge_documents(documents_to_update)
        print(f"Updated {len(documents_to_update)} documents.")
    else:
        print("No documents to update.")



def main():
    # update_field()
    # delete_all_documents()
    # delete_document('59b6e446801c023b94436d647e7a045123978dd02bc27b7f9ee430a0a9d361ea')
    folder_path = "output/FN_NOTICE_KR_20250429"
    # upload_from_file(folder_path)
    # filter_query = "system_name eq 'SCRP'"  # 또는 "fieldName eq ''" (빈 문자열인 경우)
    filter_query = "blob_path eq 'https://www.samsung.com/uk/offer/samsung-care-plus/'"  # 또는 "fieldName eq ''" (빈 문자열인 경우)
    # check_unique_ids(folder_path)
    # delete_documents_from_folder(folder_path)
    get_search_count(False, None)
    # get_search_img_count(False)
    # compare()
    # upload_image()
    # get_index()

if __name__ == "__main__":
    main()
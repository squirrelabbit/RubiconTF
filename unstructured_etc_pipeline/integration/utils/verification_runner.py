from utils.dbsearch import (
    get_verification_setting_by_system,
    get_pending_verification_qaset_by_system,
    get_qaset_mapping_code_by_system,
    update_qaset_verification_result,
    history_insert
)
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential
from dotenv import load_dotenv
from utils.common import get_secret_from_key_vault
import hashlib
import os
import logging  # 추가

load_dotenv(override=True)
AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")
AZURE_SEARCH_SECRET_NAME = os.environ.get("AZURE_SEARCH_SECRET_NAME")
AZURE_SEARCH_API_KEY = get_secret_from_key_vault(AZURE_SEARCH_SECRET_NAME)

def hash_value(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def fetch_verification_candidates(
    system_name,
    version,
    code_mapping_flag, 
    code_mapping_list, 
    verification_field
):
    verification_candidates = []
    if code_mapping_flag == 1:
        for code_row in code_mapping_list:
            (
            category1,
            category2,
            category3,
            modelcode,
            *_  # ignore rest
            ) = code_row
            filter_clauses = [f"version eq '{version}'"]
            if category1:
                filter_clauses.append(f"category1 eq '{category1}'")
            if category2:
                filter_clauses.append(f"category2 eq '{category2}'")
            if category3:
                filter_clauses.append(f"category3 eq '{category3}'")
            if modelcode:
                filter_clauses.append(f"(model_code/any(x: x eq '{modelcode}'))")
            filter_string = " and ".join(filter_clauses)
            
            try:
                search_client = SearchClient(
                    endpoint=AZURE_SEARCH_ENDPOINT,
                    index_name=system_name,
                    credential=AzureKeyCredential(AZURE_SEARCH_API_KEY)
                )
                # 모든 검색 결과 가져오기 (skip + top 조합)
                page_size = 1000
                skip = 0
                while True:
                    results = search_client.search(search_text="*",filter=filter_string, top=page_size, skip=skip, select=verification_field)
                    batch = list(results)
                    if not batch:
                        break
                    for result in batch:
                        value = result.get(verification_field)
                        if value:
                            if isinstance(value, list):
                                for val in value:
                                    hashed = hash_value(str(val))
                                    verification_candidates.append(
                                        {
                                            'category1' : category1,
                                            'category2' : category2,
                                            'category3' : category3,
                                            'modelcode': modelcode,
                                            'hash_value' : hashed 
                                        })
                            else:
                                hashed = hash_value(str(value))
                                verification_candidates.append(
                                        {
                                            'category1' : category1,
                                            'category2' : category2,
                                            'category3' : category3,
                                            'modelcode': modelcode,
                                            'hash_value' : hashed
                                        })
                    skip += page_size
            except Exception as e:
                logging.info(f"[{version}] ERROR during search: {e}")
               
    else:
        filter_string = f"version eq '{version}'"
            
        try:
            search_client = SearchClient(
                endpoint=AZURE_SEARCH_ENDPOINT,
                index_name=system_name,
                credential=AzureKeyCredential(AZURE_SEARCH_API_KEY)
            )
            # 모든 검색 결과 가져오기 (skip + top 조합)
            page_size = 1000
            skip = 0
            while True:
                results = search_client.search(search_text="*",filter=filter_string, top=page_size, skip=skip, select=verification_field)
                batch = list(results)
                if not batch:
                    break
                for result in batch:
                    value = result.get(verification_field)
                    if value:
                        if isinstance(value, list):
                            for val in value:
                                hashed = hash_value(str(val))
                                verification_candidates.append(
                                    {
                                        'hash_value' : hashed 
                                    })
                        else:
                            hashed = hash_value(str(value))
                            verification_candidates.append(
                                    {
                                        'hash_value' : hashed
                                    })
                skip += page_size
        except Exception as e:
            logging.info(f"[{version}] ERROR during search: {e}")
    
    return verification_candidates



# def verify_qaset_entry(
#     index_name,
#     version,
#     category1,
#     category2,
#     category3,
#     modelcode,
#     expected_verification_value
# ):
#     setting_result = get_verification_setting_by_system(index_name)
#     if not setting_result:
#         logging.info(f"[{index_name}] verification setting not found.")
#         return False
#     code_mapping_flag = setting_result[0][1]
#     verification_field = setting_result[0][2]
#     # 필터 조건 생성
#     filter_clauses = [f"version eq '{version}'"]
#     if code_mapping_flag == 1:
#         if category1:
#             filter_clauses.append(f"category1 eq '{category1}'")
#         if category2:
#             filter_clauses.append(f"category2 eq '{category2}'")
#         if category3:
#             filter_clauses.append(f"category3 eq '{category3}'")
#         if modelcode:
#             filter_clauses.append(f"(model_code/any(x: x eq '{modelcode}'))")
#         filter_string = " and ".join(filter_clauses)
#     else:
#         filter_string = f"version eq '{version}'"
#     logging.info(f"[{version}] Filter: {filter_string}")
#     try:
#         search_client = SearchClient(
#             endpoint=AZURE_SEARCH_ENDPOINT,
#             index_name=index_name,
#             credential=AzureKeyCredential(AZURE_SEARCH_API_KEY)
#         )
#         # 모든 검색 결과 가져오기 (skip + top 조합)
#         page_size = 1000
#         skip = 0
#         hashed_values = []
#         while True:
#             results = search_client.search(
#                 search_text="*",
#                 filter=filter_string,
#                 top=page_size,
#                 skip=skip,
#                 select="chunk, semantic_chunk, img_data"
#             )
#             batch = list(results)
#             if not batch:
#                 break
#             for result in batch:
#                 value = result.get(verification_field)
#                 if value:
#                     if isinstance(value, list):
#                         for val in value:
#                             hashed = hash_value(str(val))
#                             hashed_values.append(hashed)
#                     else:
#                         hashed = hash_value(str(value))
#                         hashed_values.append(hashed)
#             skip += page_size
#         if not hashed_values:
#             logging.info(f"[{version}] No valid '{verification_field}' values found in results.")
#             return False
#         if expected_verification_value in hashed_values:
#             logging.info(f"[{version}] Matched in search results.")
#             return True
#         else:
#             logging.info(f"[{version}] No match found. Expected: {expected_verification_value}")
#             return False
#     except Exception as e:
#         logging.info(f"[{version}] ERROR during search: {e}")
#         return False
    
def run_verification_for_qaset(system_name, target_version):
    qaset_entries = get_pending_verification_qaset_by_system(system_name, target_version)
    if not qaset_entries:
        logging.info(f"[{system_name}] No pending QASET entries found.")
        history_insert("EMPTY_QASET", system_name, target_version, 0)
        return 0  # 검증 대상이 없는 경우 0 (실패)
    
    setting_result = get_verification_setting_by_system(system_name)
    if not setting_result:
        logging.info(f"[{system_name}] verification setting not found.")
        return 0
    code_mapping_flag = setting_result[0][1]
    verification_field = setting_result[0][2]
    
    code_mapping_list = get_qaset_mapping_code_by_system(system_name, target_version)
    
    verification_candidates = fetch_verification_candidates(system_name, target_version, code_mapping_flag, code_mapping_list, verification_field)

    if not verification_candidates:
        logging.info(f"[{target_version}] No valid '{verification_field}' values found in results.")
        return False
    
    logging.info(f"[{system_name}] Total {len(qaset_entries)} entries found.")
    success_count = 0
    fail_count = 0
    for row in qaset_entries:
        (
            _system_name,
            filter_version,
            filter_category1,
            filter_category2,
            filter_category3,
            filter_modelcode,
            expected_verification_value,
            *_  # ignore rest
        ) = row
        
        if code_mapping_flag == 1:
            verification_qaset = {
                'category1' : filter_category1,
                'category2' : filter_category2,
                'category3' : filter_category3,
                'modelcode': filter_modelcode,
                'hash_value' : expected_verification_value
            }
        else : 
            verification_qaset = {
                'hash_value' : expected_verification_value
            }
        
        if verification_qaset in verification_candidates:
            logging.info(f"[{target_version}] Matched in search results.")
            
            update_qaset_verification_result(system_name, filter_version, expected_verification_value, 1)
            success_count +=1
        else:
            logging.info(f"[{target_version}] No match found. Expected: {verification_qaset}")
            update_qaset_verification_result(system_name, filter_version, expected_verification_value, 2)
            fail_count += 1

    logging.info(f"\n[{system_name}] 검증 완료: 성공 {success_count} / 실패 {fail_count}")
    if fail_count > 0:
        history_insert("VERIFICATION_FAILED", system_name, target_version, fail_count)
    return 1 if fail_count == 0 else 0
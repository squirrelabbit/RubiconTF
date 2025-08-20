from src.services.feature_service import process_features
import logging

logger = logging.getLogger("app_logger")

## 특장점 api + 주석생성
async def process_row_async(row):

    if not isinstance(row, dict):
        row = dict(row)

    feature_index_list = await process_features(row)
    result_data =[]
    if feature_index_list:
        for feature_index in feature_index_list:
            json_data = feature_index.to_upload_sch_data()
            result_data.append(json_data)
    return result_data        
    
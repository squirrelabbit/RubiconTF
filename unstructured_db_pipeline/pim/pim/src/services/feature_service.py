import logging
from src.utils.common_util import clean_text, clean_url
from src.modules.img_search import get_or_upload_alt
from src.utils.markdown_converter import custom_markdownify
from src.database.fetch import fetch_data_by_code
from src.utils.common_util import get_bu
from src.models.feature_model import IndexBase
import json
import copy
import re

logger = logging.getLogger("app_logger")


def remove_markdown_urls(chunk):
    pattern = r'!\[.*?\]\((https?://.*?)\)'
    return re.sub(pattern, lambda match: f"![{match.group(0).split('](')[0][2:]}]()".strip(), chunk)

async def process_features(row):
    result_data =json.loads(row.get("response_json",{}))
    feature_data = json.loads(row.get("feature_json",{})).get("FeatureItem",{})

    try:
        product_data = result_data.get("Products", {}).get("Product", {})
        basic_info = product_data.get("BasicInfo", [])
        packageYn = ""
        if basic_info and isinstance(basic_info, list) and isinstance(basic_info[0], dict):
            packageYn = basic_info[0].get("PackageYN", "")


        if packageYn == "N":
            full_feature_text = []
            full_feature_text = await process_feature_items(feature_data, row, row.get("model_code",""))
        
        elif packageYn =="Y":
            # pacageYn이 Y인경우 PackageProduct에 있는 모델코드의 특장점 api 데이터의 합을 return한다
            package_list = product_data.get("PackageProducts", {}).get("ChildItems", [])
            full_feature_text = {}
            for package_child in package_list:
                package_model_code = package_child.get("ModelCode", "")
                try:
                    model_code_data = await fetch_data_by_code(package_model_code)
                    package_product_data = json.loads(model_code_data[0].get("feature_json",{})).get("FeatureItem",{})
                    package_item_text = await process_feature_items(package_product_data, row, package_model_code)
                    full_feature_text[package_model_code] = package_item_text
                except Exception as e:
                    logger.error(f"Package Feature 처리 중 오류: {e}, model_code: {package_model_code}")
                    return []
                
        final_index_data = []

        bu = await get_bu(row.get("model_name"))
        feature_input_obj = IndexBase(row=row, bu=bu, chunk_seq=0, chunk="", semantic_chunk_seq=0, semantic_chunk="")
        
        # case 1: 리스트 형식 입력
        if isinstance(full_feature_text, list):
            full_chunk = "\n".join(semantic_chunk.get("chunk") for semantic_chunk in full_feature_text)
            for semantic_chunk_info in full_feature_text:
                temp_obj = copy.deepcopy(feature_input_obj)
                temp_obj.chunk_seq =1
                temp_obj.chunk =full_chunk
                temp_obj.semantic_chunk_seq =semantic_chunk_info.get("seq", "")
                temp_obj.semantic_chunk =remove_markdown_urls(semantic_chunk_info.get("chunk", ""))
                final_index_data.append(temp_obj)
                
        # case 2: 딕셔너리 형식 입력
        elif isinstance(full_feature_text, dict):
            for package_idx, semantic_chunk_list in enumerate(full_feature_text.values()):
                package_full_chunk = "\n".join(semantic_chunk.get("chunk") for semantic_chunk in semantic_chunk_list)
                for semantic_chunk_info in semantic_chunk_list:
                    temp_obj = copy.deepcopy(feature_input_obj)
                    temp_obj.chunk_seq = package_idx +1
                    temp_obj.chunk =package_full_chunk
                    temp_obj.semantic_chunk_seq =semantic_chunk_info.get("seq", "")
                    temp_obj.semantic_chunk =remove_markdown_urls(semantic_chunk_info.get("chunk", ""))
                    final_index_data.append(temp_obj)
            
        return final_index_data
    except Exception as e:
        logger.error(f"get_feature 처리 중 오류: {e}, model_code: {row.get('model_code', '')}")
        return []
    
async def process_feature_items(feature_data, row, model_code):
    # FeatureItems 추출
    # Feature가 없을 경우 처리
    if not feature_data:
        return ""
    content_list=[]
    # Feature 처리
    for feature in feature_data:
        md_content = ""
        try:
            # Markdown 콘텐츠 생성
            title = clean_text(feature.get("FeatureTitle", {}).get("featureTitle", "")).strip()
            subtitle = clean_text(feature.get("FeatureSubTitle", {}).get("featureSubTitle", "")).strip()
            body = clean_text(feature.get("FeatureBody", {}).get("featureBody", "")).strip()
            foot = clean_text(feature.get("FeatureFootnote", "")).strip()
            media = feature.get("FeatureMedia", [])
            seq =int(feature.get("featureItemPosition", ""))

            if title:
                md_content += f"## {title}\n"
            if subtitle:
                md_content += f"**{subtitle}**\n"
            if body:
                md_content += f"{body}\n"
            if foot:
                md_content += f"{foot}\n"
            if isinstance(media, list) and media:
                media_list = list({item['url']: item for item in media if item}.values())
                for media_item in media_list:
                    md_content += await handle_media(media_item, row, md_content) + "\n"

            # SubFeatures 처리
            sub_features = feature.get("SubFeatureItems", {}).get("SubFeatureItem", []) or []
            for sub_feature in sub_features:
                sub_title = clean_text(sub_feature.get("FeatureTitle", {}).get("featureTitle", "")).strip()
                sub_subtitle = clean_text(sub_feature.get("FeatureSubTitle", {}).get("featureSubTitle", "")).strip()
                sub_body = clean_text(sub_feature.get("FeatureBody", {}).get("featureBody", "")).strip()
                sub_media = sub_feature.get("FeatureMedia", [])
                sub_disclaimer = sub_feature.get("FeatureDisclaimer", "").strip()

                if sub_title:
                    md_content += f"### {sub_title}\n"
                if sub_body:
                    md_content += f"{sub_body}\n"
                if sub_disclaimer:
                    md_content += f"{sub_disclaimer}\n"
                if sub_subtitle:
                    md_content += f"**{sub_subtitle}**\n"

                if isinstance(sub_media, list) and sub_media:
                    sub_media = list({item['url']: item for item in sub_media if item is not None}.values())
                    for sub_media_item in sub_media:
                        if sub_media_item.get("sizeType") == "mobileSize":
                            md_content += await handle_media(sub_media_item, row, md_content) + "\n"
            if md_content:
                content_data = {"seq":seq, "chunk": custom_markdownify(str(md_content))}
                if not content_data in content_list:
                    content_list.append(content_data)
        except Exception as e:
            logger.error(f"Error processing individual feature: {e}, model_code: {model_code}")
    return content_list

async def handle_media(media_item, row, md_content):
    global total_count, alt_none_count
    try:
        if media_item.get("type") != "image":
            return ""
        if media_item.get("sizeType") != "pcSize":
                return ""
        
        alt = clean_text(media_item.get("description", ""))
        src = media_item.get("url")

        if not src or src.lower().startswith("javascript"):
            return ''

        if src.startswith("//"):
            src = "https:" + src

        src = clean_url(src)

        alt = await get_or_upload_alt(src, alt, row, md_content)

        return f"![{alt}]({src})" if alt and alt !=r"N/A" else ""
    except Exception as e:
        logger.error(f"handle_media 처리 중 오류: {e}")
        return ""
  
    
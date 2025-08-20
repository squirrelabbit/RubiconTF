from datetime import date
from dataclasses import dataclass
import aiohttp
import base64
from dataclasses import dataclass
import json

DEFAULT_URL = "https://api.samsung.com/model?key=24A284F43F0D3D4CE063E4AEC70A2194&siteCode=uk&modelCode={0}&option=127&type=json"

@dataclass
class PIMBasicInfo:
    createion_date:date
    modification_date:date
    launch_date:date

@dataclass
class PIMMedia:
    featureItemPosition:int
    url: str
    description: str
    media_type: str
    media_size_type:str

@dataclass
class PIMData:
    model_code:str
    model_name:str
    display_name:str
    category1:str
    category2:str
    category3:str
    display_status:bool
    basic_info:PIMBasicInfo
    media_data:list[PIMMedia]


def _find_data(data,contents):
    if isinstance(data, dict):
        for key, value in data.items():
            if key == contents:
                return value
            result = _find_data(value,contents)
            if result is not None:
                return result
    elif isinstance(data, list):
        for item in data:
            result = _find_data(item,contents)
            if result is not None:
                return result
    return None



async def get_basic_info(model_code:str,data:dict):
    tmp = _find_data(data,"BasicInfo")
    basic_info = tmp[0]
    return PIMBasicInfo(
        createion_date=basic_info.get('CreationDate'),
        modification_date=basic_info.get('ModificationDate'),
        launch_date=basic_info.get('LaunchDate')
    )


async def get_features(model_code: str,data:dict) -> list[PIMMedia]:
    tmp = _find_data(data,"FeatureItem")
    result = []
    if tmp:
        for f in tmp:
            media_list = f.get('FeatureMedia') or []
            featureItemPosition = f.get('featureItemPosition')
            for media in media_list:
                pim_data = PIMMedia(
                    featureItemPosition = featureItemPosition,
                    url = media.get('url'),
                    description = media.get('description'),
                    media_type = media.get('type'),
                    media_size_type = media.get('sizeType')
                )
                if pim_data.media_size_type == "mobileSize" and pim_data.description:
                    result.append(pim_data)
    return result

async def _fetch_features(model_code: str) -> list:
    url = DEFAULT_URL.format(model_code)

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url) as response:
                response.raise_for_status()
                data = await response.json()
                features = _find_data(data,"FeatureItem")
                sub_features = _find_data(data,"SubFeatureItems")
                basic_info = _find_data(data,"BasicInfo")
                return features if features else [], basic_info[0] or None, sub_features if sub_features else []
        except Exception as e:
            print(f"에러 발생: {e}")
            return []



async def get_pim_data(model_code: str) -> PIMData:
    features, basic_info,sub_features = await _fetch_features(model_code)
    pim_basic_info = PIMBasicInfo(
        createion_date=basic_info.get('CreationDate'),
        modification_date=basic_info.get('ModificationDate'),
        launch_date=basic_info.get('LaunchDate')
    )
    result = []
    for f in sub_features:
        media_list = f.get('FeatureMedia') or []
        featureItemPosition = f.get('featureItemPosition')
        for media in media_list:
            pim_data = PIMMedia(
                featureItemPosition = featureItemPosition,
                url = media.get('url'),
                description = media.get('description'),
                media_type = media.get('type'),
                media_size_type = media.get('sizeType')
            )
            if pim_data.media_size_type == "mobileSize" and pim_data.description:
                result.append(pim_data)
    return PIMData(basic_info=pim_basic_info,media_data=result)

@dataclass
class ImageDataOutput:
    id:str
    image_url:str
    image_type:str
    image_description:str
    category1:str
    category2:str
    category3:str
    display_name:str
    modification_date:date

async def unique_urls_all(data) -> list[ImageDataOutput]:
    unique_urls = {}

    for item in data:
        feature_data = json.loads(item['feature_json'])
        features = await get_features(item['model_code'],feature_data)

        basic_data = json.loads(item['response_json'])
        basic_info = await get_basic_info(item['model_code'],basic_data)

        for f in features:
            if f.url :
                unique_urls[f.url] = ImageDataOutput(
                    id = f"{item['model_code']}_{f.featureItemPosition}",
                    image_url = f.url,
                    image_type = f.media_type.lower(),
                    category1 = item['category1'],
                    category2 = item['category2'],
                    category3 = item['category3'],
                    display_name = item['display_name'],
                    image_description = f.description,
                    modification_date = basic_info.modification_date
                )

    return unique_urls


async def unique_urls_media_type(data,media_type) -> list[ImageDataOutput]:
    unique_urls = {}

    for item in data:
        feature_data = json.loads(item['feature_json'])
        features = await get_features(item['model_code'],feature_data)

        basic_data = json.loads(item['response_json'])
        basic_info = await get_basic_info(item['model_code'],basic_data)

        for f in features:
            if f.url and f.media_type.lower() == media_type:
                unique_urls[f.url] = ImageDataOutput(
                    id = f"{item['model_code']}_{f.featureItemPosition}",
                    image_url = f.url,
                    image_type = f.media_type.lower(),
                    category1 = item['category1'],
                    category2 = item['category2'],
                    category3 = item['category3'],
                    display_name = item['display_name'],
                    image_description = f.description,
                    modification_date = basic_info.modification_date
                )

    return [value for key,value in unique_urls.items()]

def text_to_base64(text):
    bytes_data = text.encode('utf-8')
    base64_encoded = base64.urlsafe_b64encode(bytes_data)
    base64_text = base64_encoded.decode('utf-8')

    return base64_text
from langchain_openai import AzureChatOpenAI
from langchain_core.prompts import (
    ChatPromptTemplate, HumanMessagePromptTemplate, SystemMessagePromptTemplate
)
import logging
from src.config.settings import AZURE_OPENAI
import asyncio
from functools import partial


logger = logging.getLogger("inference_logger")

CAPTION_SYSTEM_PROMPT = """
## [System Information]
This system is Samsung Electronics' chatbot, designed to assist with searching and guiding users on various electronic products. It is built on a Retrieval-Augmented Generation (RAG) architecture, utilizing structured and unstructured data sources. The processed data is intended for use in the UK, so all processing must be conducted in **English only**.
## [Agent Information]
This agent is responsible for **image annotation preprocessing** in Samsung Electronics' chatbot system.
After reviewing the data from [old_caption] and [image], follow the steps outlined in [Task].
---
## [Task]
**Caption Creation Task**:
    - **Objective**: Generate an appropriate caption that describes the `image`.
    - **Guidelines**:
        - Do **not** extract text from the image; OCR data is already handled separately. Your goal is to describe the image itself.
        - Most images are product images or feature highlights of Samsung Electronics products. Including `model_name` or `category3` in the caption is encouraged when relevant.
        - Use the metadata in [input_data] to help create an accurate and relevant caption.
        - Captions must be accurate and informative, but not overly long. Keep the caption under **50 Korean characters in length**, even though the content is in English.
    - **Examples**:
        - *Product Image*: Galaxy Watch5 showcasing advanced fitness tracking features
        - *Feature Description*: Heart rate monitoring feature of Galaxy Watch5
        - *Chart or Graph*: Battery performance comparison of Galaxy S24 series
    - **Output**:
        - Return the generated caption as plain English text. **Do not use any special characters** (e.g., quotation marks, backticks).

## [input_data]
1. `chunk`: Description or context related to the image (optional)
2. `ocr`: Text extracted from the image (optional)
3. `goods_name`: Product name
4. `category1`: Top-level product category
5. `category2`: Mid-level product category
6. `category3`: Sub-level product category
7. `image`: Image data
---
## Additional Instructions:
- **Consistency**: Use a consistent style and tone across all generated captions.
- **Clarity**: Captions must be accurate, clear, and easy to understand.
- **Language Requirement**: Your response **must be in English only**. Do not generate Korean captions under any circumstance.
"""
async def safe_ainvoke(chain, input_data):
    return await asyncio.get_event_loop().run_in_executor(
        None,
        partial(chain.invoke, input_data)
    )

async def get_inference(inf_data):
    """AI 기반 캡션 생성"""
    model = AzureChatOpenAI(
        azure_endpoint=AZURE_OPENAI["endpoint"],
        api_key=AZURE_OPENAI["api_key"],
        api_version=AZURE_OPENAI["api_version"],
        deployment_name=AZURE_OPENAI["deployment_name"],
        temperature=0.3
    )
    system_message_template = SystemMessagePromptTemplate.from_template(CAPTION_SYSTEM_PROMPT)
    human_message_template = HumanMessagePromptTemplate.from_template("""
    1. `chunk`: {chunk}
    2. `ocr`: {ocr}
    3. `goods_name`: {goods_name}
    4. `category1`: {category1}
    5. `category2`: {category2}
    6. `category3`: {category3}
    7. `image`: {url}
    """)

    prompt = ChatPromptTemplate.from_messages([system_message_template, human_message_template])
    chain = prompt | model

    max_retries = 3
    for attempt in range(3):
        try:
            result = await safe_ainvoke(chain,{
                "chunk": f"{inf_data.chunk}\n{inf_data.caption}",
                "ocr": inf_data.ocr,
                "goods_name": inf_data.goods_nm,
                "category1": inf_data.category1,
                "category2": inf_data.category2,
                "category3": inf_data.category3,
                "url": inf_data.url
            })
            return result.content.strip() if result.content else "캡션을 생성하지 못했습니다."
        except Exception as e:
            # logging.info(f"get_inference = {e}")
            if attempt < max_retries:
                retry_wait = (attempt + 1) * 2  # Exponential backoff
                await asyncio.sleep(retry_wait)
            else:
                raise
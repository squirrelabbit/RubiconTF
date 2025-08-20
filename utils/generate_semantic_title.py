import os, sys
import re, json, ast
from dotenv import load_dotenv
from utils.common import get_secret_from_key_vault
from openai import AsyncAzureOpenAI
from typing import Optional

load_dotenv(override=True)

AZURE_OPENAI_ENDPOINT = os.environ["AZURE_OPENAI_ENDPOINT"]
AZURE_OPENAI_SECRET_NAME = os.environ.get("AZURE_OPENAI_SECRET_NAME")
AZURE_OPENAI_API_KEY = get_secret_from_key_vault(AZURE_OPENAI_SECRET_NAME)
AZURE_OPENAI_DEPLOYMENT_NAME = "gpt-4o-mini"
AZURE_OPENAI_API_VERSION = os.environ["AZURE_OPENAI_API_VERSION"]
SYSTEM_LOCATION = os.environ.get("SYSTEM_LOCATION")


aoai_client = AsyncAzureOpenAI(
    api_key        = AZURE_OPENAI_API_KEY,
    azure_endpoint = AZURE_OPENAI_ENDPOINT,
    api_version    = AZURE_OPENAI_API_VERSION,
)

language = "korean" if SYSTEM_LOCATION == "KR" else "english"

system_instructor_summary = f"""
                                **Absolute rule**
                                - Title and Content must be generated in {language}.
                                - Title and Content should be composed in correct {language}.
                                - If you have not found a point to create a response in the provided context, please return None.
                                - Only **Json** data from **Response Format** must be returned.
                                - The response should not contain newline characters.
                                You are an input–structuring and cleaning assistant. Given the following raw text:
                                1. **Remove** all symbols, HTML tags, markup, emojis, and any filler or unrelated content.
                                2. **Preserve** only the original words or phrases that are directly relevant to the main topic.
                                3. **Do not** summarize, paraphrase, or add any new information—keep the wording verbatim.
                                Output exactly in this format:
"""
system_instructor_summary += """
                            **Response Format**
                                If successful : {"title": <a concise title drawn verbatim from the input>, "content": <the cleaned input text, preserving original wording and structure>}
                                If failed : {"title": None , "content": None}
                            """
                            
def safe_dict(text: str) -> dict | None:

    if not isinstance(text, str):
        return None

    # 양쪽 중괄호 보강
    text = text.strip()
    if not text.startswith("{"):
        text = "{" + text
    if not text.endswith("}"):
        text = text + "}"

    # ----------------------------------------
    # ① Python 3.12 이상: strict=False 로 먼저 시도
    # ----------------------------------------
    if sys.version_info >= (3, 12):
        try:
            return json.loads(text, strict=False)
        except json.JSONDecodeError:
            pass

    # ----------------------------------------
    # ② 줄바꿈·탭 컨트롤 문자 이스케이프 후 JSON 재시도
    # ----------------------------------------
    _escaped = (
        text.replace("\\", "\\\\")      # 백슬래시 먼저 이스케이프
            .replace("\r", "\\r")
            .replace("\t", "\\t")
            .replace("\n", "\\n")
    )
    try:
        return json.loads(_escaped)
    except json.JSONDecodeError:
        pass

    # ----------------------------------------
    # ③ 작은따옴표 파이썬 dict 표기
    # ----------------------------------------
    try:
        return ast.literal_eval(text)
    except Exception:
        pass

    # ----------------------------------------
    # ④ 정규식으로 마지막 추출 (title / content 키만 잡기)
    # ----------------------------------------
    m = re.search(
        r'"?title"?\s*:\s*[\'"](?P<title>.*?)[\'"]\s*,\s*'
        r'"?content"?\s*:\s*[\'"](?P<content>.*)[\'"]\s*}\s*$',
        text,
        flags=re.S  # DOTALL: 줄바꿈 포함
    )
    if m:
        return {
            "title":   m.group("title").strip(),
            "content": m.group("content").strip()
        }

    # 결국 실패
    return None

# 공통 호출 함수
async def call_llm_instruction(context: str) -> str | None:
    messages = [
        {"role": "system", "content": system_instructor_summary},
        {"role": "user",   "content": json.dumps({"provided context": context}, ensure_ascii=False)},
    ]
    resp = await aoai_client.chat.completions.create(
        model=AZURE_OPENAI_DEPLOYMENT_NAME,
        messages=messages,
        temperature=0.1,
    )
    data = safe_dict(resp.choices[0].message.content)
    if not data:
        return None, None
    semantic_title = data.get("title")
    semantic_summary = data.get("content")
    
    return semantic_title, semantic_summary
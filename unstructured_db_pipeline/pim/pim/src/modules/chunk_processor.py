import re
import tiktoken
from src.utils.markdown_converter import custom_markdownify
from src.modules.img_search import get_or_upload_alt
import copy
from typing import List

async def update_image_alts(markdown_content, row):
    """Markdown에서 이미지 ALT를 비동기로 업데이트"""
    image_pattern = re.compile(r"!\[(.*?)\]\((.*?)\)")  # Markdown 이미지 패턴
    matches = list(image_pattern.finditer(markdown_content))

    # updated_markdown 초기화
    updated_markdown = markdown_content

    # ALT 업데이트를 위한 비동기 작업
    for match in matches:
        alt = match.group(1)
        src = match.group(2)
        
        try:
            # ALT 업데이트 수행
            updated_alt = await get_or_upload_alt(src, old_alt=alt, row=row, chunk = markdown_content)
            if updated_alt and updated_alt != r"N/A":
                result = f"![{updated_alt}]({src})"
            else:
                result = ""

            # Markdown 콘텐츠에 ALT 업데이트
            updated_markdown = updated_markdown.replace(
                match.group(0), result
            )
        except Exception as e:
            # 특정 ALT 업데이트 실패 시 경고 로그
            print(f"Failed to update ALT for src: {src}, alt: {alt}, Error: {e}")

    return updated_markdown

from src.models.feature_model import IndexBase
from src.utils.common_util import get_bu
async def process_content(html_content, row):

    markdown_content = custom_markdownify(html_content).replace("\n","")
    
    updated_markdown = await update_image_alts(markdown_content, row)
    bu = await get_bu(row.get("model_name"))
    feature_input_obj = IndexBase(row=row, bu=bu, chunk_seq=0, chunk=updated_markdown, semantic_chunk_seq=0, semantic_chunk="")

    chunks = await run_autochunking(feature_input_obj)
    return chunks

def remove_markdown_urls(chunk):
    pattern = r'!\[.*?\]\((https?://.*?)\)'
    return re.sub(pattern, lambda match: f"![{match.group(0).split('](')[0][2:]}]()".strip(), chunk)

def gpt4o_tokenizer(text):
    enc = tiktoken.get_encoding("o200k_base")
    tokens = enc.encode(text)
    return len(tokens)

def split_text_by_tokens(text, token_size, overlap):
    enc = tiktoken.get_encoding("o200k_base")
    tokens = enc.encode(text)
    chunks = []
    non_overlap_chunks = []
    start = 0
    while start < len(tokens):
        end = start + token_size
        chunk_tokens = tokens[start:end]
        chunks.append(chunk_tokens)
        
        if start == 0:
            non_overlap_chunks.append(tokens[start:end])
        else:
            non_overlap_chunks.append(tokens[start + overlap:end])
        
        start = end - overlap

    if len(chunks) > 1 and len(chunks[-1]) < token_size:
        last_start = max(0, len(tokens) - token_size)
        chunks[-1] = tokens[last_start:]

    return {
        "chunks": [enc.decode(chunk) for chunk in chunks],
        "non_overlap_chunks": [enc.decode(chunk) for chunk in non_overlap_chunks]
    }

async def run_autochunking(input_obj:IndexBase) -> List[IndexBase]:
    #chunk 기준
    PARENTS_CHUNK_SIZE = 4096
    PARENTS_CHUNK_OVERLAP_SIZE = 512
    parents_chunk_list = list()
    chunk_list = split_text_by_tokens(input_obj.chunk, PARENTS_CHUNK_SIZE, PARENTS_CHUNK_OVERLAP_SIZE)
    for idx,splChunk in enumerate(chunk_list["chunks"]):
        temp_obj = copy.deepcopy(input_obj)
        temp_obj.chunk = splChunk
        temp_obj.chunk_seq = idx + 1
        temp_obj.semantic_chunk = remove_markdown_urls(splChunk)
        temp_obj.content = chunk_list["non_overlap_chunks"][idx]
        # temp_obj = generate_original_id(temp_obj)
        parents_chunk_list.append(temp_obj)
    return parents_chunk_list
import tiktoken
import re
import copy

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
from src.config.settings import SYSTEM_NAME
def run_autochunking(input_obj):
    #chunk 기준
    PARENTS_CHUNK_SIZE = 4096
    PARENTS_CHUNK_OVERLAP_SIZE = 512

    parents_chunk_list = list()
    
    if SYSTEM_NAME =="BUY":
        parents_chunk_list.append(input_obj)
    else:
        chunk_list = split_text_by_tokens(input_obj.chunk, PARENTS_CHUNK_SIZE, PARENTS_CHUNK_OVERLAP_SIZE)
        
        for idx,splChunk in enumerate(chunk_list["chunks"]):
            temp_obj = copy.deepcopy(input_obj)
            temp_obj.chunk = splChunk
            temp_obj.chunk_seq = idx + 1
            temp_obj.semantic_chunk = remove_markdown_urls(splChunk)
            temp_obj.content = chunk_list["non_overlap_chunks"][idx]
            parents_chunk_list.append(temp_obj)
            
    return parents_chunk_list

if __name__ =="__main__":
    chunk = ""
    print(len(chunk.encode('utf-8')))
    result = gpt4o_tokenizer(chunk)
    print(result)
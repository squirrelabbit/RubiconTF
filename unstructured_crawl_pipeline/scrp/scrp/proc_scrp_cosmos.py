from utils.task_info import SeedData,TaskStatus, TaskType
from utils.tools.embedder import aoai_aembedding, bge_embedding_retry
from utils.data_search import SearchService
from utils.log_manager import LogManager
from utils.proc_common import change_status
from utils.generate_semantic_title import call_llm_instruction
from scrp.proc_scrp_common import ScrpSearch, ScrpSeedContainer, ScrpRefData
from scrp.common_utils import generate_id, generate_original_id, generate_filter_id
from utils.proc_index_version import insert_verification_row
import os

SYSTEM_NAME = os.environ['SYSTEM_NAME']

async def run_cosmos_scrp(doc_data):
    seed = SeedData(**doc_data)
    ref_data = ScrpRefData(**seed.ref_data)
    
    await change_status(SYSTEM_NAME,TaskStatus.IN_PROGRESS,TaskType.DEFAULT,seed,ScrpSeedContainer)
    
    # qset 대상일 경우 검증 셋 삽입
    try:
        if seed.qset_flag:
            await insert_verification_row(
                system_name= seed.system_name, 
                version= seed.version,
                cat1= ref_data.category1,
                cat2= ref_data.category2,
                cat3= ref_data.category3,
                model_code=None, 
                chunk_text = ref_data.semantic_chunk,
                )
    except Exception as e:
        await LogManager.info(f"qset insert Error : {str(e)}")
    
    index_list = []
    try:
            
        index = ScrpSearch(
            system_name = seed.system_name,
            version = seed.version,
            title = ref_data.title,
            content = ref_data.content,
            chunk = ref_data.chunk,
            chunk_seq = ref_data.chunk_seq,
            blob_path = ref_data.blob_path,
            semantic_chunk_seq= ref_data.semantic_chunk_seq,
            semantic_chunk= ref_data.semantic_chunk,
            semantic_title= ref_data.semantic_title,
            semantic_question= ref_data.semantic_question,
            semantic_keyword= ref_data.semantic_keyword,
            display_seq = ref_data.display_seq,
            category1 = ref_data.category1,
            category2 = ref_data.category2,
            category3 = ref_data.category3,
        )
        index.semantic_title, index.semantic_summary = await call_llm_instruction(index.semantic_chunk)
        index.embedding_chunk=await aoai_aembedding(index.chunk) if index.chunk else []
        index.embedding_semantic_bgechunk = await bge_embedding_retry(index.semantic_chunk, retries=3) if index.semantic_chunk else []
        index.embedding_semantic_bgetitle = await bge_embedding_retry(index.semantic_title, retries=3) if index.semantic_title else []
        
        index = generate_original_id(index)
        index = generate_id(index)
        index = generate_filter_id(index)

        index_list.append(index)
        
        try:
            await SearchService.upload_batch(index_list, 300)
        except Exception as e:
            await LogManager.info(f"Index Upload Error : {str(e)}")
        await change_status(SYSTEM_NAME,TaskStatus.COMPLETED,TaskType.DEFAULT,seed,ScrpSeedContainer)
                
    except Exception as e:
        await LogManager.exception(e,"scrp cosmos trigger error")
        await change_status(SYSTEM_NAME,TaskStatus.ERROR,TaskType.DEFAULT,seed,ScrpSeedContainer)
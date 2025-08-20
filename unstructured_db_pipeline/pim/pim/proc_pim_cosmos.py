from utils.task_info import SeedData,TaskStatus, TaskType
from utils.data_search import SearchService
from utils.log_manager import LogManager
from utils.proc_common import change_status
from utils.data_common import generate_id
from pim.proc_pim_common import PimSearch, PimSeedContainer, PimRefData
from pim.common_utils import generate_id, generate_original_id, generate_filter_id
from utils.tools.embedder import aoai_aembedding, bge_embedding_retry
from utils.generate_semantic_title import call_llm_instruction
from utils.proc_index_version import insert_verification_row
import os

SYSTEM_NAME = os.environ['SYSTEM_NAME']

async def run_cosmos_pim(doc_data):
    seed = SeedData(**doc_data)
    ref_data = PimRefData(**seed.ref_data)

    await change_status(SYSTEM_NAME,TaskStatus.IN_PROGRESS,TaskType.DEFAULT,seed,PimSeedContainer)
    
    # qset 대상일 경우 검증 셋 삽입
    try:
        if seed.qset_flag:
            await insert_verification_row(
                system_name= seed.system_name, 
                version= seed.version,
                cat1= ref_data.category1,
                cat2= ref_data.category2,
                cat3= ref_data.category3,
                model_code=ref_data.model_code[0], 
                chunk_text = ref_data.semantic_chunk,
                )
    except Exception as e:
        await LogManager.info(f"qset insert Error : {str(e)}")

    index_list = []
    try:
        index = PimSearch(
            system_name = seed.system_name,
            version = seed.version,
            title = ref_data.title,
            chunk = ref_data.chunk,
            semantic_chunk = ref_data.semantic_chunk,
            chunk_seq = ref_data.chunk_seq,
            semantic_chunk_seq = ref_data.semantic_chunk_seq,
            blob_path = ref_data.blob_path,
            bu = ref_data.bu,
            category1 = ref_data.category1,
            category2 = ref_data.category2,
            category3 = ref_data.category3,
            model_code = ref_data.model_code,
            model_name = ref_data.model_name,
            goods_nm = ref_data.goods_nm,
            goods_id = ref_data.goods_id,
        )
        semantic_title, semantic_summary = await call_llm_instruction(index.semantic_chunk)
        index.semantic_title = semantic_title
        index.semantic_summary = semantic_summary

        index.embedding_chunk=await aoai_aembedding(index.chunk) if index.chunk else []
        index.embedding_semantic_bgechunk = await bge_embedding_retry(index.semantic_chunk, retries=1) if index.semantic_chunk else []
        index.embedding_semantic_bgetitle = await bge_embedding_retry(index.semantic_title, retries=1) if index.semantic_title else []
        
        index = generate_original_id(index)
        index = generate_id(index)
        index = generate_filter_id(index)

        index_list.append(index)

        try:
            await SearchService.upload_batch(index_list, 300)
        except Exception as e:
            await LogManager.info(f"Index Upload Error : {str(e)}")
        await change_status(SYSTEM_NAME,TaskStatus.COMPLETED,TaskType.DEFAULT,seed,PimSeedContainer)
        
    except Exception as e:
        await LogManager.exception(e,"sample cosmos trigger error")
        await change_status(SYSTEM_NAME,TaskStatus.ERROR,TaskType.DEFAULT,seed,PimSeedContainer)
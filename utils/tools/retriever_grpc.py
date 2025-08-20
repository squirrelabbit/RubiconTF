import json
import grpc
import traceback
import os
from google.protobuf import json_format
from dotenv import load_dotenv
from tools.__protobuf import alpha_pb2, alpha_pb2_grpc, encoder

load_dotenv()
GRPC_SERVER = os.environ["GRPC_SERVER"]
GRPC_PORT = os.environ["GRPC_PORT"]


async def grpc_stub_function(grpc_server, function, action, query):
    try:
        jsonable_query = encoder.jsonable_encoder(query)
        query = json.dumps(jsonable_query)
    except Exception as e:
        print(e)
        return {'success': False, 'error': 'jsonize error'}

    if isinstance(query, str):
        grpc_response = None
            
        with grpc.insecure_channel("{}:{}".format(GRPC_SERVER, GRPC_PORT)) as channel:
            request = alpha_pb2.request(function = function, action = action, query = query)
            stub = alpha_pb2_grpc.AlphaStandardGRPCFunctionStub(channel)
            grpc_response = stub.rpcAlphaStandardGRPCFunction(request)
            grpc_response = json_format.MessageToJson(grpc_response)
            grpc_response = json.loads(grpc_response)['response']
            grpc_response = json.loads(grpc_response)
        return grpc_response
 
    else:
        return {'success': False, 'error': 'jsonize error'}


async def run_embedding(chunk):
    query_dict = { 'model': 'bge-m3', 'sentence_list': [f"{chunk}"]}
    grpc_return = await grpc_stub_function('embedding_gpu', 'bert', 'embedding', query_dict)

    if grpc_return:
        data = grpc_return.get('data',None)
        if data :
            return data[0]
        
    return None

def run_rerank(chunks,question,top_k=12, score_threshold=2):  
    query_dict = { 'model': 'reranker', 'text_pairs': [[chunk, question] for chunk in [r['expression'] for r in chunks]] }
    grpc_return = grpc_stub_function('embedding_gpu', 'bert', 'reranker', query_dict)

    index_scores = sorted([(i,score) for i,score in enumerate(grpc_return['data']) if score >= score_threshold], key=lambda x : x[1], reverse=True)
    top_chunks = [{
        "mapping_code": chunks[i]['mapping_code'],
        "field": chunks[i]['field'],
        "expression": chunks[i]['expression'],
        "category_lv1": chunks[i]['category_lv1'],
        "category_lv2": chunks[i]['category_lv2'],
        "category_lv3": chunks[i]['category_lv3'],
        "type": chunks[i]['type'],
        "score": score
    } for i,score in index_scores[:top_k]]

    return top_chunks

def run_rerank_default(chunks,question,top_k):
    query_dict = { 'model': 'reranker', 'text_pairs': [[chunk, question] for chunk in [r['chunk'] for r in chunks]] }
    grpc_return = grpc_stub_function('embedding_gpu', 'bert', 'reranker', query_dict)

    index_scores = sorted([(i,score) for i,score in enumerate(grpc_return['data']) ], key=lambda x : x[1], reverse=True)
    top_chunks = [{
        "@search.score": score,
        "category1": chunks[i]['category1'],
        "category2": chunks[i]['category2'],
        "category3": chunks[i]['category3'],
        "chunk": chunks[i]['chunk'],
        "system_name": chunks[i]['system_name']
    } for i,score in index_scores[:top_k]]

    return top_chunks
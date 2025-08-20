from langchain_openai import AzureChatOpenAI
from langchain_core.output_parsers import PydanticOutputParser
from abc import ABC, abstractmethod
import os
from typing import List,Union,AsyncGenerator,TypeVar
from pydantic import BaseModel
from langchain.prompts import PromptTemplate
from langchain_core.messages import HumanMessage, SystemMessage
from utils.common import get_secret_from_key_vault

AZURE_OPENAI_API_VERSION = os.environ["AZURE_OPENAI_API_VERSION"]
AZURE_OPENAI_ENDPOINT = os.environ["AZURE_OPENAI_ENDPOINT"]
AZURE_OPENAI_SECRET_NAME = os.environ.get("AZURE_OPENAI_SECRET_NAME")
AZURE_OPENAI_API_KEY = get_secret_from_key_vault(AZURE_OPENAI_SECRET_NAME)
AZURE_OPENAI_DEPLOYMENT_NAME = os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"]


class BaseAgentModel:
    SYSTEM_PROMPT:PromptTemplate
    session_id:str = None
    

    def __init__(self, **data) -> None:
        self.model=AzureChatOpenAI(azure_endpoint=AZURE_OPENAI_ENDPOINT, api_key=AZURE_OPENAI_API_KEY,
            api_version=AZURE_OPENAI_API_VERSION, deployment_name=AZURE_OPENAI_DEPLOYMENT_NAME, temperature=data.get('temperature',0))


    @abstractmethod
    async def retrieval(self, return_direct=True) -> Union[str, dict]:
        """이 메서드는 자식 클래스에서 구현되어야 합니다."""
        pass

    async def _stream_generation(self,chain,params) -> AsyncGenerator[str, None]:
        async for chunk in chain.astream(params):
            self.generation_result += chunk
            
            yield chunk
    
    async def _generation(self,chain,params) -> str:
        return await chain.ainvoke(params)

    T = TypeVar('T', bound='BaseModel')

    async def generation_with_images(
        self,
        image_infos: List[dict],  # [{"url": ..., "desc": ...}, ...]
        response_format: T,
        question: str
    ) -> T:
        output_parser = PydanticOutputParser(pydantic_object=response_format)
        format_instructions = output_parser.get_format_instructions()

        system_msg = SystemMessage(content=self.SYSTEM_PROMPT.format())

        content_blocks = [{"type": "text", "text": f"{question}\n\n{format_instructions}"}]
        
        for idx, info in enumerate(image_infos):
            if "desc" in info:
                content_blocks.append({"type": "text", "text": f"[이미지 {idx + 1}] {info['desc']}"})
            content_blocks.append({"type": "image_url", "image_url": {"url": info["url"]}})

        messages = [system_msg, HumanMessage(content=content_blocks)]

        self.generation_result = ""
        result: T = await self.model.ainvoke(messages, output_parser=output_parser)
        return result

    async def generation_struct_pydantic(self,response_format:T,params) -> T:
        output_parser = PydanticOutputParser(pydantic_object=response_format)
        params["format_instructions"] = output_parser.get_format_instructions()

        chain = (
            self.SYSTEM_PROMPT
            | self.model
            | output_parser
        )
        
        result = await chain.ainvoke(params)
        
        return result
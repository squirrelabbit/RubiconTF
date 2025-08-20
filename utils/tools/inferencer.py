import os
import asyncio
from openai import AsyncAzureOpenAI
import json
# Azure OpenAI 환경 변수 설정
os.environ["AZURE_OPENAI_ENDPOINT"] = "https://dev-aoai-rb-krc-sub.openai.azure.com/"
os.environ["AZURE_OPENAI_DEPLOYMENT"] = "gpt-4o"
os.environ["AZURE_OPENAI_API_VERSION"] = "2024-08-01-preview"
# 비동기 Azure OpenAI 클라이언트 생성
client = AsyncAzureOpenAI(
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
)
system_instructor_question = """
[태스크]
    1.당신은 한국어 질의를 예상하는 업무를 담당합니다.
    2.주어진 [근거]를 바탕으로 대답할 수 있는 [질문]을 생성해 내야 합니다.
    3.[질문]은 다양한 시각과 연령대, 성별 등 정해지지않은 관점에서 폭넓게 생성해내야 합니다.
    4.질문은 10개를 생성해냅니다. [근거]가 짧아서 질문생성이 어려운 경우에는 지엽적이지 않은 수준까지만 생성해냅니다.
    5.[동의어 예시]를 참고하여 예시처럼 동의어를 최대한 활용합니다.
    6.[질문]에 제품 모델에 대한 직접 언급은 하지말아주세요
    [질문 관점]
    1.질문중에는 전자기기에 익숙치 않은 여성 혹은 노약자 관점의 질문도 꼭 포함되어야합니다.
    2.반대로 어린아이의 관점에서 추상적인 질문도 포함 되어야합니다.
    단, [근거] 자체가 전자기기와 관련이 없으며 문맥을 파악할 수 없는 경우에는 None을 반환해주세요.
    [질문]은 넘버링이 불필요합니다.
    [질문]에는 지시하는 대명사 지시어등을 포함하지 마세요.
    [질문]에는 연령대를 추측할 수 있는 단어를 포함하지 마세요.
    [질문 예시]
    이 카메라의 초광각 렌즈는 어떤 특징이 있나요? 보다는
    초광각 렌즈는 어떤 특징이 있나요?와 같은
    간결한 질문을 만들어주세요
    [동의어 예시]
    circle -> 써클, 서클
    검색 -> 서치, 찾기
    음향 -> 소리, 사운드
[최종 답변 포맷]
    질문이 있는경우 : {"questions": ["초광각 렌즈는 어떤 특징이 있나요?","써클투서치는 어떻게 활용하나요?"]}
    질문이 없는경우 : {"questions": ""}
"""
system_instructor_kwd = """
[첫번째 업무]
    당신은 [근거]에 포함되어있는 핵심적인 키워드를 찾아내는 업무를 수행합니다.
    1.최대한 많은 키워드를 찾아주세요. [근거]에서 추출할 수 있는 키워드가 아예 없는 경우를 제외하고는 1개이상의 키워드를 추출해주세요.
    2.키워드를 찾아내는 업무는 검색포탈에서 해당 [근거]를 찾고자 하는 사람들이 주로 활용 할 것 같은 검색 키워드를 사전에 정의하는 것에 있습니다.
    3.[근거]에서는 표준표기 방법만을 사용하는것이 아닌 제품, 기능, 특징 위주로 최대한 동의어를 포함한 많은 키워드를 찾아내야합니다.
    4.동의어가 모두 [근거]에 제시 되지는 않습니다. 동의어는 합리적 범위 안에서 추론해 [키워드]를 정리해야합니다.
    [동의어 예시]
    1.써클투서치, 서클투서치, circle to search
    2.갤럭시 탭 s9, 탭9, tab9
    3.카메라 성능, 사진성능
[최종 답변 포맷]
    키워드가 있는경우 : {"keywords": ["써클투서치","탭9"]}
    키워드가 없는경우 : {"keywords": ""}
"""
system_instructor_title = """
[업무]
    당신은 [근거]를 활용하여 함축 된 제목을 생성해내야 합니다.
    1.제목은 [근거]를 잘 요약하여 함축 되어 있어야 합니다.
    2.제목은 중복된 내용이 존재하지 않도록 합니다.
    3.제목은 반드시 한글로 작성 되어야 합니다.
[최종 답변 포맷]
    제목이 있는 경우 : {"title": "갤럭시s24 구매시 조심해야할 점"}
    제목이 없는경우 : {"title": ""}
"""
async def generation(prompt):
    response = await client.chat.completions.create(
        model=os.getenv("AZURE_OPENAI_DEPLOYMENT"),  # 배포된 모델 지정
        messages=prompt,
        temperature=0.3,
    )
    return response.choices[0].message.content
async def generateTitle(contents):
    
    
    tit = [
        {"role": "system", "content": system_instructor_title},
        {"role": "user", "content": contents}
    ]
    result = await generation(tit)#title
    print(result)
    #print(json.loads(result)["title"])
    return json.loads(result)["title"]
async def generateQuestion(contents):
    que = [
        {"role": "system", "content": system_instructor_question},
        {"role": "user", "content": contents}
    ]
    result = await generation(que)#question
    print(result)
    return json.loads(result)["questions"]

async def generateKwd(contents):
    kwd = [
        {"role": "system", "content": system_instructor_kwd},
        {"role": "user", "content": contents}
    ]
    result = await generation(kwd)#answer
    print(result)
    return json.loads(result)["keywords"]
# # 비동기 실행 테스트
# async def main():
#     contents = """
#     # General\n\n# Galaxy AI\n\n# Camera\n\n# Perfor mance\n\n# Design & Display\n\n# Battery & Charging\n\n# Sustain ability\n\n# Durability\n\n# Security & Privacy\n\n<figure>\nWhat are the most significant improvements to the S24 Series?\n===\n\n\\* 1st asked & most frequently asked questions from customers (Customer response survey for + 3 days after unpacking)\n## Answers\n\nUPGRADING\n\nS23 Series > S24 Series\n\nG\n\n<figure>\n## Live Translate / Chat Assist\n\nThe S24 Series lets you freely communicate your thoughts with real-time, language barrier-free voice calls and chats.\n\n<figure>\n## Note Assist\n\nWith Notes, you can magically organize what you write. It generates a summary cover of your notes, and transforms your notes into various formats.\n\n<figure>\n## S24 Ultra Quad Tele System\n\nThe S24 Ultra's new tele lens lets you take 50 MP high-resolution shots at 5x. The result is clear and bright, even at night. Also, its optical quality is maintained at all quad zoom level.\n\n<figure>\n## Powerful, Stable Gameplay\n\nWith the fastest AP ever in a Galaxy, you can enjoy more immersive gaming than before.\n \n<figure>\n.....\n## Circle to Search with Google\n\nThe S24 Series lets you effortlessly search for anything on the screen with a simple circling gesture to get information instantly.\n\n...\n## More Immersive Viewing\n\nThe S24 Series boasts the brightest display with Vision Booster in the S Series, so you can a great viewing experience, even outdoors.\n\n<figure>\n_Retail | Training_\n\n_TRAINING USE ONLY_
#     """
#     result = await generateKwd(f"[근거]{contents}")
#     print("결과:", result)
# asyncio.run(main())
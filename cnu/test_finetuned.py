import asyncio
import os
from browser_use import BrowserSession, BrowserProfile, Agent
from browser_use.llm.openai.chat import ChatOpenAI
from dotenv import load_dotenv

load_dotenv()

async def main():
    llm = ChatOpenAI(
        model="bua-32b-text",  # vLLM --served-model-name에 맞추기
        base_url="http://localhost:8000/v1",
        api_key="not-needed",
    )

    browser = BrowserSession(
        browser_profile=BrowserProfile(
            headless=True,
            allowed_domains=["dcs-lcms.cnu.ac.kr", "dcs-learning.cnu.ac.kr"],
        )
    )

    agent = Agent(
        task="사이버캠퍼스 https://dcs-lcms.cnu.ac.kr 에서 다음을 수행해줘. 결과가 없으면 없다고 알려주면 돼: 로그인한 후 강의실 페이지로 이동해줘",
        llm=llm,
        browser=browser,
        use_vision=False,  # 텍스트 모델이라 스크린샷 비활성화
        sensitive_data={
            "dcs-lcms.cnu.ac.kr": {
                "x_user_id": os.getenv("CNU_ID"),
                "x_user_pw": os.getenv("CNU_PASSWORD"),
            }
        },
    )

    history = await agent.run(max_steps=20)
    print(f"\n결과: {'성공' if history.is_successful() else '실패'}")
    print(f"최종: {history.final_result()}")
    await browser.stop()

asyncio.run(main())
import asyncio
from browser_use import BrowserSession, BrowserProfile
from browser_use.llm.google.chat import ChatGoogle
from browser_use import Agent
from dotenv import load_dotenv
import os

load_dotenv()

async def explore():
    browser = BrowserSession(browser_profile=BrowserProfile(headless=True))
    agent = Agent(
        task='사이버캠퍼스 https://dcs-lcms.cnu.ac.kr 에 로그인한 후, 메인 페이지와 강의실 페이지에서 접근 가능한 모든 메뉴, 탭, 버튼 목록을 텍스트로 정리해줘. 각 과목 페이지에 들어가면 어떤 하위 메뉴(공지사항, 강의자료, 과제, 성적 등)가 있는지도 확인해줘.',
        llm=ChatGoogle(model='gemini-2.5-flash'),
        browser=browser,
        sensitive_data={
            'dcs-lcms.cnu.ac.kr': {
                'x_user_id': os.getenv('CNU_ID'),
                'x_user_pw': os.getenv('CNU_PASSWORD'),
            }
        },
        save_conversation_path='./data/conversations/explore.json',
        generate_gif='./data/gifs/explore.gif',
    )
    history = await agent.run(max_steps=40)
    print(history.final_result())
    await browser.stop()

asyncio.run(explore())
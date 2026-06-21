import asyncio
from browser_use import BrowserSession, BrowserProfile
import os
from dotenv import load_dotenv
from browser_use.llm.google.chat import ChatGoogle
from logged_agent import LoggedAgent

load_dotenv()

TASKS = [
    "충남대학교 학생 포털 https://dcs-lcms.cnu.ac.kr 에 접속해줘",
    # 태스크 추가하기
]

async def run_task(task: str, task_index: int):
    print(f"\n[{task_index+1}/{len(TASKS)}] 태스크 시작: {task}")

    browser_session = BrowserSession(
        browser_profile=BrowserProfile(headless=True)
    )

    agent = LoggedAgent(
        task=task,
        llm=ChatGoogle(model="gemini-2.5-flash"),
        log_path="./data/training_data.jsonl",
        browser=browser_session,
        generate_gif=f"./data/gifs/task_{task_index}.gif",  # GIF 녹화
        save_conversation_path=f"./data/conversations/task_{task_index}.json",  # 대화 로그
    )

    try:
        history = await agent.run(max_steps=20)
        print(f"완료: {history.final_result()}")

        # step별 스크린샷 경로 출력
        screenshots = history.screenshot_paths()
        print(f"스크린샷 {len([s for s in screenshots if s])}장 저장됨")
    except Exception as e:
        print(f"에러 발생: {e}")


async def main():
    os.makedirs("./data", exist_ok=True)
    os.makedirs("./data/gifs", exist_ok=True)
    os.makedirs("./data/conversations", exist_ok=True)

    for i, task in enumerate(TASKS):
        await run_task(task, i)
        await asyncio.sleep(2)

async def main():
    os.makedirs("./data", exist_ok=True)
    os.makedirs("./data/traces", exist_ok=True)

    for i, task in enumerate(TASKS):
        await run_task(task, i)
        await asyncio.sleep(2)

if __name__ == "__main__":
    asyncio.run(main())
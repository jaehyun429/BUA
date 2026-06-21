# test_unseen.py
# 학습 데이터에 없는 변형 태스크 20개 (일반화 평가용)
# 커스텀 액션(파일 업로드) 포함

import asyncio
import os
import json
from datetime import datetime
from browser_use import BrowserSession, BrowserProfile, Agent
from browser_use.llm.openai.chat import ChatOpenAI
from cnu.ui.backend.custom_actions import controller
from dotenv import load_dotenv

load_dotenv()

BASE_CONTEXT = "사이버캠퍼스 https://dcs-lcms.cnu.ac.kr 에서 다음을 수행해줘. 결과가 없으면 없다고 알려주면 돼:"
MAX_STEPS = 30
SLEEP_BETWEEN = 3

# ============================================================
# 학습 데이터에 없는 변형 태스크 20개
# ============================================================
UNSEEN_TASKS = [
    "딥러닝 과목 공지사항에서 가장 최근 글의 내용을 알려줘",
    "종합설계1 과목 공지사항에서 가장 최근 글의 내용을 알려줘",

    "딥러닝 과목 과제 중 제출 하지 않은 과제가 있다면 언제까지인지 알려줘",
    "종합설계1 과목 과제 중 제출 하지 않은 과제가 있다면 언제까지인지 알려줘",
    "직업과 진로 과목 과제 중 제출 하지 않은 과제가 있다면 언제까지인지 알려줘",

    # --- 자료실 변형 (학습: "파일 확인" → 변형: 파일 수, 오래된 파일) ---
    "범죄의진실과오해 과목 자료실에 가장 최근 주차의 파일을 다운로드 해줘.",
    "종합설계1 과목 자료실에서 가장 최근 주차의 파일을 다운로드 해줘.",

    # --- 강의수강 변형 ---
    "범죄의진실과오해 과목 강의수강에서 가장 최근 강의 중 듣지 않은 과목이 있다면 강의를 들어줘.",

    # --- 성적/출석 변형 ---
    "딥러닝 과목 출석 페이지에서 내 출석 현황을 알려줘",
    "종합설계1 과목의 출석 페이지에서 내 출석 현황을 알려줘.",

    # --- 메인 기능 변형 ---
    "메인 페이지에서 수강 중인 과목이 총 몇 개인지 알려줘",
    "To-Do-list에서 이번 주 마감인 항목이 있는지 확인해줘",

    # --- 게시판 변형 ---
    "딥러닝 과목 Q&A게시판에 제목 : bua Test, 내용: bua Test로 글 작성해줘",
    "종합설계1 과목 자유게시판에서 제목: bua Test, 내용: bua Test로 글 작성해줘",
    "종합설계1 과목 Q&A게시판에 제목 : bua Test, 내용: bua Test로 글 작성해줘",

    # --- 파일 업로드 (커스텀 액션 테스트) ---
    "딥러닝 과목 과제 페이지에서 가장 최근 과제에 /mnt/home_dnlab/jhjung/test_files/test_upload.txt 파일을 제출해줘",
    "종합설계1 과목 과제 페이지에서 가장 최근 과제에 /mnt/home_dnlab/jhjung/test_files/test_upload.txt 파일을 제출해줘",

    # --- 복합 변형 ---
    "딥러닝 과목의 중간고사 일자와 장소가 어디인지 알려줘",
    "범죄의 진실과 오해 중간고사 일자와 장소가 어디인지 알려줘",
    "직업과 진로 중간고사 보는지 과제로 대체하는지 알려줘",
]


async def run_task(idx, task, llm):
    print(f"\n{'='*60}")
    print(f"[{idx+1}/{len(UNSEEN_TASKS)}] {task}")
    print('='*60)

    browser = BrowserSession(
        browser_profile=BrowserProfile(
            headless=True,
            allowed_domains=["dcs-lcms.cnu.ac.kr", "dcs-learning.cnu.ac.kr"],
        )
    )

    full_task = f"{BASE_CONTEXT} 로그인한 후, {task}"

    agent = Agent(
        task=full_task,
        llm=llm,
        browser=browser,
        controller=controller,
        use_vision=False,
        sensitive_data={
            "dcs-lcms.cnu.ac.kr": {
                "x_user_id": os.getenv("CNU_ID"),
                "x_user_pw": os.getenv("CNU_PASSWORD"),
            }
        },
        available_file_paths=["/mnt/home_dnlab/jhjung/test_files/test_upload.txt"],
    )

    result = {"task_index": idx, "task": task, "success": None, "error": None}

    try:
        history = await agent.run(max_steps=MAX_STEPS)
        result["success"] = history.is_successful()
        result["final_result"] = history.final_result()
        result["steps"] = history.number_of_steps()
        icon = "✅" if result["success"] else "❌"
        print(f"{icon} 결과: {'성공' if result['success'] else '실패'} ({result['steps']} steps)")
        if result["final_result"]:
            print(f"   응답: {result['final_result'][:200]}")
    except Exception as e:
        result["success"] = False
        result["error"] = str(e)[:300]
        print(f"❌ 에러: {str(e)[:200]}")
    finally:
        await browser.stop()

    await asyncio.sleep(SLEEP_BETWEEN)
    return result


async def main():
    os.makedirs("./data/results", exist_ok=True)

    llm = ChatOpenAI(
        model="bua-32b-text",
        base_url="http://localhost:8000/v1",
        api_key="not-needed",
    )

    start = int(os.getenv("START_TASK", "0"))
    end = int(os.getenv("END_TASK", str(len(UNSEEN_TASKS))))
    tasks_to_run = list(enumerate(UNSEEN_TASKS))[start:end]

    print(f"🚀 일반화 테스트 시작: {len(tasks_to_run)}개 태스크 (학습 데이터에 없는 변형)")
    print(f"   모델: bua-32b-text (finetuned)")
    print(f"   커스텀 액션: 파일 첨부")

    results = []
    for i, task in tasks_to_run:
        result = await run_task(i, task, llm)
        results.append(result)

    # ============================================================
    # 결과 요약
    # ============================================================
    print(f"\n{'='*60}")
    print("📊 일반화 테스트 결과")
    print('='*60)

    success_count = sum(1 for r in results if r["success"])
    fail_count = len(results) - success_count
    print(f"성공: {success_count}개 | 실패: {fail_count}개 | 성공률: {success_count/len(results)*100:.1f}%")

    # 유형별 분류
    categories = {
        "공지사항 변형": UNSEEN_TASKS[0:3],
        "과제 변형": UNSEEN_TASKS[3:6],
        "자료실 변형": UNSEEN_TASKS[6:8],
        "강의수강 변형": UNSEEN_TASKS[8:10],
        "성적/출석 변형": UNSEEN_TASKS[10:12],
        "메인 기능 변형": UNSEEN_TASKS[12:14],
        "게시판 변형": UNSEEN_TASKS[14:16],
        "파일 업로드": UNSEEN_TASKS[16:18],
        "복합 변형": UNSEEN_TASKS[18:20],
    }

    task_to_cat = {}
    for cat, tasks in categories.items():
        for t in tasks:
            task_to_cat[t] = cat

    print("\n유형별 성공률:")
    for cat in categories:
        cat_results = [r for r in results if task_to_cat.get(r["task"]) == cat]
        if not cat_results:
            continue
        s = sum(1 for r in cat_results if r["success"])
        t = len(cat_results)
        rate = s / t * 100 if t > 0 else 0
        bar = "█" * int(rate / 5) + "░" * (20 - int(rate / 5))
        print(f"  [{cat:12s}] {bar} {s}/{t} ({rate:.0f}%)")

    if fail_count > 0:
        print(f"\n❌ 실패 태스크 ({fail_count}개):")
        for r in results:
            if not r["success"]:
                print(f"  [{r['task_index']:3d}] {r['task']}")
                if r.get("error"):
                    print(f"        에러: {r['error'][:100]}")

    # 저장
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    outpath = f"./data/results/test_unseen_{ts}.json"
    final = {
        "test_type": "unseen_generalization",
        "model": "bua-32b-text (finetuned)",
        "custom_actions": ["파일 첨부"],
        "total_tasks": len(results),
        "success_count": success_count,
        "fail_count": fail_count,
        "success_rate": success_count / len(results) * 100 if results else 0,
        "task_results": results,
    }
    with open(outpath, "w", encoding="utf-8") as f:
        json.dump(final, f, ensure_ascii=False, indent=2)
    print(f"\n💾 결과 저장: {outpath}")


if __name__ == "__main__":
    asyncio.run(main())
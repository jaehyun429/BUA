# collect.py
# 사이버캠퍼스 태스크 자동 수집 스크립트

import asyncio
import os
import sys
import json
import time
from datetime import datetime
from browser_use import BrowserSession, BrowserProfile
from browser_use.llm.openai.chat import ChatOpenAI
from browser_use.llm.google.chat import ChatGoogle
from logged_agent import LoggedAgent
from dotenv import load_dotenv
from tasks.cnu_tasks import ALL_TASKS_V3, TASK_CATEGORIES_V3

load_dotenv()

BASE_CONTEXT = "사이버캠퍼스 https://dcs-lcms.cnu.ac.kr 에서 다음을 수행해줘. 결과가 없으면 없다고 알려주면 돼:"

# 수집 설정
MAX_STEPS = 30
SLEEP_BETWEEN_TASKS = 3
RESET_INTERVAL = 10

# 모델 설정
# collect.py의 MODELS 딕셔너리에 추가
MODELS = {
    "gemini": lambda: ChatGoogle(model="gemini-2.5-flash"),
    "gpt": lambda: ChatOpenAI(model="gpt-4o", api_key=os.getenv("OPENAI_API_KEY")),
    "bua-32b": lambda: ChatOpenAI(
        model="bua-32b-text",
        base_url="http://localhost:8000/v1",
        api_key="not-needed",
    ),
    "qwen-vanilla": lambda: ChatOpenAI(        # ← 추가
        model="bua-32b-text",
        base_url="http://localhost:8000/v1",
        api_key="not-needed",
    ),
    "bua-vl-7b": lambda: ChatOpenAI(
        model="bua-vl-7b",
        base_url="http://localhost:8000/v1",
        api_key="not-needed",
    ),
}

# 비전 미지원 모델
TEXT_ONLY_MODELS = {"bua-32b", "qwen-vanilla"}  # ← qwen-vanilla 추가



async def run_task(task_index: int, task: str, llm, model_name: str):
    print(f"\n{'='*60}")
    print(f"[모델: {model_name}] [{task_index+1}/{len(ALL_TASKS_V3)}] {task}")
    print('='*60)

    browser_session = BrowserSession(
        browser_profile=BrowserProfile(
            headless=True,
            allowed_domains=["dcs-lcms.cnu.ac.kr", "dcs-learning.cnu.ac.kr"],
        )
    )

    if task_index >= 8:  # BASIC_TASKS 이후부터 로그인 추가
        full_task = f"{BASE_CONTEXT} 로그인한 후, {task}"
    else:
        full_task = f"{BASE_CONTEXT} {task}"

    task_start_time = time.time()

    agent_kwargs = dict(
        task=full_task,
        llm=llm,
        log_path=f"./data/{model_name}/training_data.jsonl",
        browser=browser_session,
        sensitive_data={
            "dcs-lcms.cnu.ac.kr": {
                "x_user_id": os.getenv("CNU_ID"),
                "x_user_pw": os.getenv("CNU_PASSWORD"),
            }
        },
        generate_gif=f"./data/{model_name}/gifs/task_{task_index:03d}.gif",
        save_conversation_path=f"./data/{model_name}/conversations/task_{task_index:03d}.json",
        available_file_paths=["/mnt/home_dnlab/jhjung/test_files/test_upload.txt"],
    )

    # 텍스트 전용 모델이면 비전 비활성화
    if model_name in TEXT_ONLY_MODELS:
        agent_kwargs["use_vision"] = False

    agent = LoggedAgent(**agent_kwargs)

    result = {
        "model": model_name,
        "task_index": task_index,
        "task": task,
        "success": None,
        "error": None,
    }

    try:
        history = await agent.run(max_steps=MAX_STEPS)
        result["success"] = history.is_successful()
        result["final_result"] = history.final_result()
        result["steps"] = history.number_of_steps()

        try:
            if hasattr(history, 'usage') and history.usage is not None:
                result["token_usage"] = str(history.usage)
            else:
                result["token_usage"] = None
        except Exception:
            result["token_usage"] = None

        task_end_time = time.time()
        result["total_time_seconds"] = round(task_end_time - task_start_time, 2)
        print(f"결과: {'성공' if result['success'] else '실패'} ({result['steps']} steps, {result['total_time_seconds']}초)")

    except Exception as e:
        result["success"] = False
        result["error"] = str(e)
        result["token_usage"] = None
        task_end_time = time.time()
        result["total_time_seconds"] = round(task_end_time - task_start_time, 2)
        print(f"에러: {e} ({result['total_time_seconds']}초)")

    finally:
        await browser_session.stop()

    await asyncio.sleep(SLEEP_BETWEEN_TASKS)
    return result


async def main():
    # 명령줄 인자로 모델 선택
    if len(sys.argv) > 1:
        model_name = sys.argv[1]
    else:
        model_name = "gemini"

    if model_name not in MODELS:
        print(f"❌ '{model_name}'은(는) 유효하지 않은 모델입니다.")
        print(f"사용 가능: {', '.join(MODELS.keys())}")
        print(f"\n사용법: python collect.py [모델명]")
        print(f"  예시: python collect.py gemini")
        print(f"        python collect.py gpt")
        print(f"        python collect.py bua-32b")
        return

    llm = MODELS[model_name]()

    print(f"\n{'='*80}")
    print(f"사용 모델: {model_name}")
    print(f"총 태스크: {len(ALL_TASKS_V3)}개")
    print(f"{'='*80}\n")

    # 모델별 디렉토리 생성
    for d in [
        f"./data/{model_name}",
        f"./data/{model_name}/gifs",
        f"./data/{model_name}/conversations",
        f"./data/{model_name}/results",
        f"./data/{model_name}/token_usage",
    ]:
        os.makedirs(d, exist_ok=True)

    start = int(os.getenv("START_TASK", "0"))
    end = int(os.getenv("END_TASK", str(len(ALL_TASKS_V3))))

    print(f"수집 범위: index {start}~{end-1} ({end - start}개)")

    all_results = []
    collection_start_time = time.time()

    for i, task in list(enumerate(ALL_TASKS_V3))[start:end]:
        result = await run_task(i, task, llm, model_name)
        all_results.append(result)

        # 토큰 사용량 개별 저장
        if result.get("token_usage"):
            try:
                token_record = {
                    "model": model_name,
                    "task_index": i,
                    "task": task,
                    "timestamp": datetime.now().isoformat(),
                    "success": result["success"],
                    "steps": result.get("steps"),
                    "total_time_seconds": result.get("total_time_seconds"),
                    "token_usage": result["token_usage"],
                }
                with open(f"./data/{model_name}/token_usage/task_{i:03d}.json", "w", encoding="utf-8") as f:
                    json.dump(token_record, f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"⚠️ 토큰 사용량 저장 실패: {e}")

        # 10개마다 중간 저장
        if len(all_results) % 10 == 0:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            with open(f"./data/{model_name}/results/progress_{timestamp}.json", "w", encoding="utf-8") as f:
                json.dump(all_results, f, ensure_ascii=False, indent=2)
            print(f"💾 진행상황 저장: {len(all_results)}개 태스크 완료")

    collection_end_time = time.time()
    total_collection_time = round(collection_end_time - collection_start_time, 2)

    # ============================================================
    # 최종 결과 요약
    # ============================================================
    print(f"\n{'='*60}")
    print(f"[{model_name}] 수집 완료 요약")
    print('='*60)

    success_count = sum(1 for r in all_results if r["success"])
    fail_count = sum(1 for r in all_results if not r["success"])
    total_time = sum(r.get("total_time_seconds", 0) for r in all_results)
    avg_time = total_time / len(all_results) if all_results else 0

    print(f"성공: {success_count}개")
    print(f"실패: {fail_count}개")
    print(f"성공률: {success_count/len(all_results)*100:.1f}%")
    print(f"총 소요 시간: {total_collection_time}초 ({total_collection_time/60:.1f}분)")
    print(f"평균 태스크 시간: {avg_time:.2f}초")

    # 카테고리별 성공률
    task_to_cat = {}
    for cat, tasks in TASK_CATEGORIES_V3.items():
        for t in tasks:
            task_to_cat[t] = cat

    cat_stats = {}
    for r in all_results:
        cat = task_to_cat.get(r["task"], "unknown")
        if cat not in cat_stats:
            cat_stats[cat] = {"success": 0, "fail": 0, "total_time": 0, "count": 0}
        if r["success"]:
            cat_stats[cat]["success"] += 1
        else:
            cat_stats[cat]["fail"] += 1
        cat_stats[cat]["total_time"] += r.get("total_time_seconds", 0)
        cat_stats[cat]["count"] += 1

    print("\n카테고리별 통계:")
    for cat, stats in cat_stats.items():
        total = stats["success"] + stats["fail"]
        rate = stats["success"] / total * 100 if total > 0 else 0
        avg_cat_time = stats["total_time"] / stats["count"] if stats["count"] > 0 else 0
        print(f"  [{cat:12s}] {stats['success']}/{total} ({rate:.0f}%) - 평균 {avg_cat_time:.1f}초")

    if fail_count > 0:
        print("\n실패 태스크:")
        for r in all_results:
            if not r["success"]:
                print(f"  [{r['task_index']:2d}] {r['task']} ({r.get('total_time_seconds', 0)}초)")
                if r.get("error"):
                    print(f"       에러: {r['error'][:100]}")

    # 최종 결과 저장
    final_summary = {
        "model": model_name,
        "collection_date": datetime.now().isoformat(),
        "total_tasks": len(all_results),
        "success_count": success_count,
        "fail_count": fail_count,
        "success_rate": success_count / len(all_results) * 100 if all_results else 0,
        "total_collection_time_seconds": total_collection_time,
        "average_task_time_seconds": avg_time,
        "category_stats": cat_stats,
        "task_results": all_results,
    }

    with open(f"./data/{model_name}/results/final_results.json", "w", encoding="utf-8") as f:
        json.dump(final_summary, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 결과 저장 완료:")
    print(f"  - 결과: ./data/{model_name}/results/final_results.json")
    print(f"  - 학습 데이터: ./data/{model_name}/training_data.jsonl")
    print(f"  - 대화 기록: ./data/{model_name}/conversations/")
    print(f"  - 토큰 사용량: ./data/{model_name}/token_usage/")


if __name__ == "__main__":
    asyncio.run(main())
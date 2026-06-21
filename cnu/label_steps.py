# label_steps.py
import json, sys

JSONL = "./data/gemini/training_data.jsonl"

lines = open(JSONL, "r", encoding="utf-8").readlines()
records = [json.loads(l) for l in lines]

# 성공 trajectory만 라벨링 (실패는 어차피 안 씀)
targets = [i for i, r in enumerate(records) if r["success"] and r["is_meaningful"] is None]

print(f"라벨링 대상: {len(targets)}개 step (성공 trajectory 중 미라벨)")
print("입력: y=유의미 / n=불필요 / s=skip / q=저장후종료\n")

labeled = 0
for idx in targets:
    r = records[idx]
    action = r["output"].get("action", [])
    action_summary = []
    for a in action:
        for k, v in a.items():
            if k == "click":
                action_summary.append(f"click [{v.get('index','')}]")
            elif k == "input":
                action_summary.append(f"input [{v.get('index','')}] '{v.get('text','')[:30]}'")
            elif k == "navigate":
                action_summary.append(f"navigate {v.get('url','')[:50]}")
            elif k == "wait":
                action_summary.append(f"wait {v.get('seconds','')}s")
            elif k == "done":
                action_summary.append(f"done: {str(v.get('text',''))[:50]}")
            else:
                action_summary.append(k)

    print(f"{'='*60}")
    print(f"[task {r['task_index']} / step {r['step_number']}]")
    print(f"  eval: {r['output'].get('evaluation_previous_goal','')[:80]}")
    print(f"  goal: {r['output'].get('next_goal','')[:80]}")
    print(f"  action: {' → '.join(action_summary)}")
    
    while True:
        choice = input("  [y/n/s/q] > ").strip().lower()
        if choice in ("y", "n", "s", "q"):
            break
    
    if choice == "q":
        break
    elif choice == "y":
        records[idx]["is_meaningful"] = True
        labeled += 1
    elif choice == "n":
        records[idx]["is_meaningful"] = False
        labeled += 1
    # s = skip, None 유지

# 저장
with open(JSONL, "w", encoding="utf-8") as f:
    for r in records:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")

print(f"\n✅ {labeled}개 라벨링 완료, 저장됨")
print(f"   meaningful: {sum(1 for r in records if r['is_meaningful'] is True)}")
print(f"   not meaningful: {sum(1 for r in records if r['is_meaningful'] is False)}")
print(f"   unlabeled: {sum(1 for r in records if r['is_meaningful'] is None)}")
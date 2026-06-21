# preprocess.py
import json, re

def preprocess(input_path, output_path):
    # 1단계: 태스크별 그룹핑
    trajectories = {}
    
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            data = json.loads(line)
            
            # rebuild 포맷: input_text(str) + output(dict) + success(bool)
            task_key = data.get("task_index", 0)
            if task_key not in trajectories:
                trajectories[task_key] = {"steps": [], "success": data.get("success", False)}
            trajectories[task_key]["steps"].append(data)

    print(f"태스크 수: {len(trajectories)}개")

    # 2단계: success=True인 trajectory만 유지
    success_count = 0
    fail_count = 0
    kept_steps = 0

    with open(output_path, "w", encoding="utf-8") as fout:
        for task_key, traj in sorted(trajectories.items()):
            if not traj["success"]:
                fail_count += 1
                continue

            success_count += 1
            for data in traj["steps"]:
                input_text = data.get("input_text", "")
                output = data.get("output", {})

                if not input_text.strip():
                    continue

                messages = [
                    {"role": "user", "content": input_text},
                    {"role": "assistant", "content": json.dumps(output, ensure_ascii=False)},
                ]

                fout.write(json.dumps({"messages": messages}, ensure_ascii=False) + "\n")
                kept_steps += 1

    print(f"\n성공 trajectory: {success_count}개")
    print(f"실패 trajectory: {fail_count}개")
    print(f"최종 step 수: {kept_steps}건")

if __name__ == "__main__":
    preprocess("./data/gemini/training_data.jsonl", "./data/gemini/ft_train.jsonl")
# rebuild_training_data.py
import json, os, re, glob

CONV_DIR = os.path.expanduser("~/bua/cnu/data/gemini/conversations")
OUTPUT = os.path.expanduser("~/bua/cnu/data/gemini/training_data.jsonl")

count = 0
with open(OUTPUT, "w", encoding="utf-8") as out:
    for task_dir in sorted(glob.glob(os.path.join(CONV_DIR, "task_*.json"))):
        task_index = int(os.path.basename(task_dir).replace("task_", "").replace(".json", ""))
        
        txt_files = sorted(glob.glob(os.path.join(task_dir, "*.txt")),
                          key=lambda x: int(x.rsplit("_", 1)[-1].replace(".txt", "")))
        
        for step_num, txt_path in enumerate(txt_files, 1):
            with open(txt_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            # 마지막 JSON 블록 추출 (모델 output)
            # { "thinking": ... "action": [...] } 패턴
            json_match = re.search(r'\n(\{[\s\S]*"action"\s*:\s*\[[\s\S]*\]\s*\})\s*$', content)
            if not json_match:
                continue
            
            output_json = json_match.group(1)
            input_text = content[:json_match.start()].strip()
            
            try:
                output_parsed = json.loads(output_json)
            except json.JSONDecodeError:
                continue
            
            record = {
                "task_index": task_index,
                "step_number": step_num,
                "input_text": input_text,  # 전체 프롬프트
                "output": output_parsed,
                "success": None,  # final_results.json에서 매칭
            }
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1

print(f"✅ {count}개 step 추출 완료 → {OUTPUT}")

# final_results.json에서 success 매칭
results_path = os.path.expanduser("~/bua/cnu/data/gemini/results/final_results.json")
if os.path.exists(results_path):
    with open(results_path) as f:
        results = json.load(f)
    
    success_map = {}
    for r in results.get("task_results", results if isinstance(results, list) else []):
        success_map[r["task_index"]] = r.get("success", False)
    
    # 다시 읽어서 success 태깅
    lines = open(OUTPUT, "r", encoding="utf-8").readlines()
    with open(OUTPUT, "w", encoding="utf-8") as out:
        for line in lines:
            record = json.loads(line)
            record["success"] = success_map.get(record["task_index"], False)
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
    
    s = sum(1 for v in success_map.values() if v)
    print(f"✅ success 태깅 완료: {s}/{len(success_map)} 태스크 성공")
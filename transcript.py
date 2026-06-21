import whisperx
import os
from pathlib import Path

device = "cuda"
mp3_dir = Path("mp3")
script_dir = Path("script")

model = whisperx.load_model("large-v3", device, language="ko", compute_type="float16")
model_a, metadata = whisperx.load_align_model(language_code="ko", device=device)

for mp3_file in sorted(mp3_dir.glob("*.mp3")):
    print(f"Processing: {mp3_file.name}")
    
    audio = whisperx.load_audio(str(mp3_file))
    result = model.transcribe(audio, batch_size=16, language="ko")
    result = whisperx.align(result["segments"], model_a, metadata, audio, device)
    
    out_path = script_dir / f"{mp3_file.stem}.txt"
    with open(out_path, "w", encoding="utf-8") as f:
        for seg in result["segments"]:
            f.write(f"[{seg['start']:.2f} → {seg['end']:.2f}] {seg['text'].strip()}\n")
    
    print(f"  → 저장 완료: {out_path}")
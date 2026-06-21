# BUA — Browser Use Agent

> **KCC 2026 제출 논문** | 충남대학교 Data Network 연구실
> [![Paper](https://img.shields.io/badge/Paper-KCC%202026-blue?style=flat-square)](./paper/kcc2026.pdf)

상용 LLM(Gemini 2.5 Flash)의 브라우저 조작 trajectory를 오픈소스 모델(Qwen2.5-32B)에 전이하는 **Teacher-Student QLoRA 파인튜닝 파이프라인**입니다. 대학 LMS를 대상으로 자연어 명령만으로 다단계 웹 탐색을 자동화합니다.

---

## Results

| 모델 | 기본 태스크 (100개) | 변형 태스크 (100개) | API 비용 |
|------|-------------------|-------------------|---------|
| Gemini 2.5 Flash (Teacher) | 71% | 76% | ~50원/건 |
| Qwen2.5-32B Base | 0% | 0% | 0원 |
| **Qwen2.5-32B FT (제안)** | **82%** | **72%** | **0원** |

- Teacher 모델(71%) 대비 기본 태스크 **+11%p** 성능 향상
- 학습 데이터 미포함 변형 태스크에서도 **72%** 일반화 성능
- 상용 API 비용 **0원**으로 실제 운영 가능

---

## Architecture

```
[ 오프라인 파인튜닝 단계 (Part A) ]

Teacher 모델 (Gemini 2.5 Flash)
        │
        ▼
데이터 수집 (100개 태스크, ~1,000 스텝)
        │
        ▼
데이터 전처리 (JSON 포맷, SPA wait 규칙)
        │
        ▼
QLoRA 파인튜닝 (Qwen2.5-32B, r=16, α=32)
  └─ A6000(48GB) × 2 / Tensor Parallelism / ~3시간

[ 실시간 에이전트 추론 단계 (Part B) ]

사용자 자연어 명령
        │
        ▼
상태 인지 모듈 (DOM 트리 파싱 + SPA 렌더링 대기)
        │
        ▼
파인튜닝 모델 추론 → 행동 결정 (JSON)
        │
        ▼
행동 제어 모듈 (Browser API)
        │
        ▼
Observe → Reason → Act 루프
```

---

## Key Methods

### Teacher-Student 파이프라인
- **Stage 1**: Gemini 2.5 Flash로 LMS 성공 궤적 수집 (100건, ~1,000 스텝)
- **Stage 2**: JSON 출력 포맷 + SPA 렌더링 대기 규칙 전처리
- **Stage 3**: Qwen2.5-32B-Instruct QLoRA 파인튜닝 (r=16, α=32)

### 커스텀 액션 설계
비표준 UI 대응을 위한 도메인 맞춤형 액션 추가:
- **이중 iframe 제어**: DOM 트리가 단절된 웹 에디터 접근
- **숨겨진 파일 입력창**: 브라우저 파일 첨부 API 직접 호출

### 실패 원인 분석
전체 실패 사례(기본 18건, 변형 28건)의 90% 이상이 두 가지 비표준 UI에서 발생:
1. 이중 iframe 내부 웹 에디터 접근 실패
2. 시각적으로 숨겨진 파일 입력창 인식 실패

---

## Benchmark

- **12개 카테고리, 100개 기본 태스크** (충남대 LMS 환경)
- **100개 변형 태스크** (학습 미포함, 일반화 평가용)
- 평가 항목: 공지사항 확인, 과제 제출, 강의자료 탐색 등

---

## Tech Stack

![Python](https://img.shields.io/badge/Python-3776AB?style=flat-square&logo=python&logoColor=white)
![PyTorch](https://img.shields.io/badge/PyTorch-EE4C2C?style=flat-square&logo=pytorch&logoColor=white)
![HuggingFace](https://img.shields.io/badge/HuggingFace-FFD21E?style=flat-square&logo=huggingface&logoColor=black)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)

- **모델**: Qwen2.5-32B-Instruct
- **파인튜닝**: QLoRA (r=16, α=32) via PEFT
- **브라우저 제어**: browser-use, CDP (Chrome DevTools Protocol)
- **추론 서버**: vLLM + FastAPI + WebSocket
- **Teacher 모델**: Gemini 2.5 Flash

---

## Repository Structure

```
BUA/
├── cnu/
│   ├── tasks/          # 태스크 정의 (12개 카테고리)
│   ├── ui/             # FastAPI + WebSocket UI
│   ├── main.py         # 에이전트 메인 실행
│   ├── collect.py      # Teacher 궤적 수집
│   ├── preprocess.py   # 데이터 전처리
│   ├── label_steps.py  # 스텝 레이블링
│   ├── rebuild_training_data.py  # 학습 데이터 구축
│   ├── test_finetuned.py         # 파인튜닝 모델 평가
│   └── logged_agent.py           # 에이전트 로깅
├── test_batch.py       # 배치 평가
├── trace.py            # 궤적 추적
├── transcript.py       # 실행 로그
└── .env                # API 키 (미포함)
```

---

## Setup

```bash
git clone https://github.com/jaehyun429/BUA.git
cd BUA
pip install -r requirements.txt
```

```bash
# .env 설정
GEMINI_API_KEY=your_key
MODEL_PATH=/path/to/finetuned/qwen2.5-32b
```

---

## Usage

```bash
# Teacher 궤적 수집
python cnu/collect.py

# 데이터 전처리
python cnu/preprocess.py

# 파인튜닝 모델 평가
python cnu/test_finetuned.py

# 배치 평가 (100개 태스크)
python test_batch.py
```

---

## License

MIT License

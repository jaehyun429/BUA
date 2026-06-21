import asyncio
import json
import re
import os
import httpx
import base64
import secrets
from typing import Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv

from openai.resources.chat.completions import AsyncCompletions
original_create = AsyncCompletions.create

async def patched_create(self, *args, **kwargs):
    if "max_completion_tokens" in kwargs:
        kwargs["max_tokens"] = kwargs.pop("max_completion_tokens")
    return await original_create(self, *args, **kwargs)

AsyncCompletions.create = patched_create

load_dotenv()
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

# ─────────────────────────────────────────────────────────
# 인증 시스템
# ─────────────────────────────────────────────────────────
from auth import (
    init_db, create_user, authenticate,
    save_credential, get_credential
)
init_db()
sessions: dict[str, str] = {}  # session_id → user_id


def get_user_from_session(session_id: str) -> Optional[str]:
    return sessions.get(session_id)


# ─────────────────────────────────────────────────────────
# 환경 변수
# ─────────────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_API_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
)

BASE = "사이버캠퍼스 https://dcs-lcms.cnu.ac.kr 에서 다음을 수행해줘. 결과가 없으면 없다고 알려주면 돼:"


class AppState:
    browser = None
    agent_running = False
    chat_clients: list[WebSocket] = []
    screen_clients: list[WebSocket] = []

state = AppState()


# ─────────────────────────────────────────────────────────
# REST API: 인증
# ─────────────────────────────────────────────────────────
@app.get("/")
async def root():
    return FileResponse("../frontend/index.html")


@app.post("/api/register")
async def register(data: dict):
    user_id = data.get("user_id")
    name = data.get("name")
    password = data.get("password")
    cnu_pw = data.get("cnu_pw")
    
    if not all([user_id, name, password, cnu_pw]):
        return {"ok": False, "error": "모든 항목을 입력하세요"}
    
    if not create_user(user_id, name, password):
        return {"ok": False, "error": "이미 존재하는 학번"}
    
    save_credential(user_id, "cybercampus", user_id, cnu_pw)
    return {"ok": True}


@app.post("/api/login")
async def login(data: dict):
    user = authenticate(data.get("user_id"), data.get("password"))
    if not user:
        return {"ok": False, "error": "학번 또는 비밀번호 오류"}
    
    session_id = secrets.token_urlsafe(32)
    sessions[session_id] = user["user_id"]
    
    return {"ok": True, "session_id": session_id, "user": user}


@app.post("/api/logout")
async def logout(data: dict):
    sessions.pop(data.get("session_id"), None)
    return {"ok": True}


# ─────────────────────────────────────────────────────────
# WebSocket
# ─────────────────────────────────────────────────────────
@app.websocket("/ws/chat")
async def chat_ws(ws: WebSocket):
    await ws.accept()
    
    # 첫 메시지로 인증
    try:
        auth_msg = json.loads(await ws.receive_text())
        if auth_msg.get("type") != "auth":
            await ws.close(code=4001)
            return
        user_id = get_user_from_session(auth_msg.get("session_id"))
        if not user_id:
            await ws.send_text(json.dumps({"type": "error", "text": "세션 만료"}))
            await ws.close(code=4001)
            return
    except Exception:
        await ws.close(code=4001)
        return
    
    state.chat_clients.append(ws)
    try:
        while True:
            data = json.loads(await ws.receive_text())
            if data.get("type") == "task":
                if state.agent_running:
                    await ws.send_text(json.dumps({
                        "type": "error",
                        "text": "이미 태스크 실행 중"
                    }))
                    continue
                asyncio.create_task(run_agent_task(data["task"], user_id))
    except WebSocketDisconnect:
        if ws in state.chat_clients:
            state.chat_clients.remove(ws)


@app.websocket("/ws/screen")
async def screen_ws(ws: WebSocket):
    await ws.accept()
    state.screen_clients.append(ws)
    try:
        while True:
            await asyncio.sleep(1.0)
            if not state.agent_running or state.browser is None:
                continue
            try:
                page = await state.browser.get_current_page()
                if page is None:
                    continue
                screenshot = await page.screenshot()
                if isinstance(screenshot, bytes):
                    b64_data = base64.b64encode(screenshot).decode('utf-8')
                elif isinstance(screenshot, str):
                    b64_data = screenshot
                else:
                    continue
                await ws.send_text(b64_data)
            except Exception:
                pass
    except WebSocketDisconnect:
        if ws in state.screen_clients:
            state.screen_clients.remove(ws)


async def broadcast_chat(msg: dict):
    for ws in state.chat_clients:
        try:
            await ws.send_text(json.dumps(msg, ensure_ascii=False))
        except:
            pass


# ─────────────────────────────────────────────────────────
# Gemini API 호출
# ─────────────────────────────────────────────────────────
async def call_gemini(prompt: str, temperature: float = 0.1,
                      max_tokens: int = 4000) -> str:
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(
            GEMINI_API_URL,
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": temperature,
                    "maxOutputTokens": max_tokens,
                },
            },
        )
        r.raise_for_status()
        data = r.json()
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()


# ─────────────────────────────────────────────────────────
# 카드 포매터
# ─────────────────────────────────────────────────────────
FORMAT_PROMPT = """당신은 충남대학교 자동화 에이전트의 결과 포매터입니다.
에이전트의 원본 결과를 사용자가 보기 편한 카드 데이터(JSON)로 변환하세요.

[사용자 요청]
{task}

[에이전트 원본 결과]
{result}

다음 카드 타입 중 가장 적합한 하나만 골라 JSON으로 출력하세요.
**반드시 JSON만 출력**하고, 코드블록 표시(```)나 설명문은 절대 포함하지 마세요.
원본 결과에 없는 정보는 절대 만들어내지 마세요.

## 카드 타입

1. 과제 목록:
{{"type":"assignment_list","title":"이번 주 마감 과제","items":[{{"subject":"딥러닝","title":"HW#5","deadline":"오늘 23:59 마감","urgency":"red"}}]}}

2. 공지사항 목록:
{{"type":"notice_list","title":"공지","items":[{{"title":"제목","category":"카테고리","date":"2026/03/25","summary":"요약","deadline":"4/5"}}]}}

3. 일반 텍스트:
{{"type":"text","text":"답변"}}

이제 JSON을 출력하세요:"""


def _try_repair_json(s: str) -> Optional[str]:
    """잘린 JSON 복구 — 마지막 완전한 } 까지만 사용"""
    last_complete = s.rfind('}')
    if last_complete > 0:
        s = s[:last_complete + 1]
    
    open_b = s.count('{') - s.count('}')
    open_br = s.count('[') - s.count(']')
    
    if open_b > 0 or open_br > 0:
        return s + (']' * open_br) + ('}' * open_b)
    return None


async def format_result_to_card(task: str, raw_result: str) -> dict:
    if not raw_result or len(raw_result.strip()) < 3:
        return {"type": "text", "text": raw_result or "결과 없음"}

    # raw_result에 이미 JSON이 있으면 그대로 시도
    try:
        start = raw_result.find("{")
        end = raw_result.rfind("}")
        if start >= 0 and end > start:
            return json.loads(raw_result[start:end+1])
    except:
        pass

    # Gemini 재포맷
    prompt = FORMAT_PROMPT.format(task=task, result=raw_result)
    try:
        text = await call_gemini(prompt, temperature=0.1, max_tokens=4000)
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
        
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            json_str = text[start:end+1]
            try:
                return json.loads(json_str)
            except json.JSONDecodeError as e:
                print(f"[format] JSON error: {e}")
                repaired = _try_repair_json(json_str)
                if repaired:
                    try:
                        return json.loads(repaired)
                    except:
                        pass
    except Exception as e:
        print(f"[format] error: {e}")

    return {"type": "text", "text": raw_result}


# ─────────────────────────────────────────────────────────
# Course Discovery 헬퍼
# ─────────────────────────────────────────────────────────
async def discover_all_courses(page) -> list[dict]:
    """sessionStorage의 myCourseList에서 전체 수강 과목 추출"""
    if page is None:
        return []
    try:
        # JS에서 명시적으로 파싱 + 검증해서 반환
        result = await page.evaluate("""
            () => {
                const raw = sessionStorage.getItem('myCourseList');
                if (!raw) return null;
                
                let parsed;
                try {
                    parsed = JSON.parse(raw);
                } catch (e) {
                    return null;
                }
                
                // 이중 인코딩이면 한 번 더 파싱
                if (typeof parsed === 'string') {
                    try {
                        parsed = JSON.parse(parsed);
                    } catch (e) {
                        return null;
                    }
                }
                
                if (!Array.isArray(parsed)) return null;
                
                // 명시적으로 필요한 필드만 추출하여 단순화
                return parsed.map(c => ({
                    course_id: c.course_id || '',
                    course_nm: c.course_nm || '',
                    prof_nm: c.prof_nm || '',
                    term_year: c.term_year || '',
                    term_cd: c.term_cd || '',
                    class_no: c.class_no || '',
                }));
            }
        """)
        
        print(f"[discover] raw result type: {type(result)}")
        
        # ⭐ Python 측에서도 문자열로 왔으면 파싱
        if isinstance(result, str):
            print(f"[discover] result is string, parsing...")
            try:
                result = json.loads(result)
            except Exception as e:
                print(f"[discover] json.loads failed: {e}")
                return []
        
        if not isinstance(result, list):
            print(f"[discover] not a list: {type(result)}")
            return []
        
        print(f"[discover] found {len(result)} courses")
        if result:
            print(f"[discover] first: {result[0]}")
        return result
        
    except Exception as e:
        print(f"[discover] error: {e}")
        import traceback
        traceback.print_exc()
        return []


async def extract_current_course_id(page) -> Optional[str]:
    """현재 진입한 페이지에서 course_id 추출 (URL, DOM 등)"""
    if page is None:
        return None
    try:
        result = await page.evaluate("""
            () => {
                // 1. URL에서
                const m = location.href.match(/course[_I]?[Ii]d=([^&]+)/);
                if (m) return m[1];
                
                // 2. DOM dataset
                const els = document.querySelectorAll('[data-course-id], [data-courseid]');
                for (const el of els) {
                    const id = el.dataset.courseId || el.dataset.courseid;
                    if (id) return String(id);
                }
                
                // 3. hidden input
                const hidden = document.querySelector('input[name*="course"]');
                if (hidden && hidden.value) return hidden.value;
                
                return null;
            }
        """)
        return result
    except Exception as e:
        print(f"[extract_course_id] error: {e}")
        return None


async def navigate_to_cached_course(page, course_id: str, menu_text: str) -> bool:
    """캐시된 course_id로 과목 진입 → 좌측 메뉴 클릭"""
    if page is None:
        print("[nav] page is None")
        return False
    
    try:
        # 1. 강의실 목록 페이지로
        print(f"[nav] going to /std/lecture")
        try:
            await page.goto("https://dcs-lcms.cnu.ac.kr/std/lecture", timeout=30000)
        except Exception as e:
            print(f"[nav] goto error (ignored): {e}")
        await asyncio.sleep(2.5)
        
        # 2. course_id 카드 찾아서 클릭
        print(f"[nav] looking for course card: {course_id}")
        clicked = await page.evaluate(f"""
            (() => {{
                const courseId = '{course_id}';
                const selectors = [
                    `[data-course-id="${{courseId}}"]`,
                    `[data-courseid="${{courseId}}"]`,
                    `[value="${{courseId}}"]`,
                    `a[href*="${{courseId}}"]`,
                    `div[onclick*="${{courseId}}"]`,
                    `[onclick*="${{courseId}}"]`,
                ];
                for (const sel of selectors) {{
                    const el = document.querySelector(sel);
                    if (el) {{
                        el.click();
                        return {{ ok: true, selector: sel }};
                    }}
                }}
                
                // outerHTML 매칭 폴백
                const all = document.querySelectorAll('a, div, li, button');
                for (const el of all) {{
                    if (el.outerHTML && el.outerHTML.includes(courseId)) {{
                        el.click();
                        return {{ ok: true, selector: 'outerHTML' }};
                    }}
                }}
                return {{ ok: false }};
            }})();
        """)
        
        print(f"[nav] click result: {clicked}")
        if not clicked or not clicked.get("ok"):
            return False
        
        await asyncio.sleep(2.5)
        
        # 3. 좌측 메뉴 클릭
        print(f"[nav] looking for menu: {menu_text}")
        menu_clicked = await page.evaluate(f"""
            (() => {{
                const menuText = '{menu_text}';
                const els = Array.from(document.querySelectorAll('a, button, span, li'));
                const target = els.find(el => el.textContent.trim() === menuText);
                if (target) {{
                    target.click();
                    return true;
                }}
                const partial = els.find(el => 
                    el.textContent.trim().includes(menuText) &&
                    el.textContent.trim().length < 20
                );
                if (partial) {{
                    partial.click();
                    return true;
                }}
                return false;
            }})();
        """)
        
        print(f"[nav] menu click: {menu_clicked}")
        await asyncio.sleep(2.0)
        return bool(menu_clicked)
        
    except Exception as e:
        print(f"[nav] error: {e}")
        import traceback
        traceback.print_exc()
        return False


# ─────────────────────────────────────────────────────────
# 메인 에이전트 실행
# ─────────────────────────────────────────────────────────
async def run_agent_task(task: str, user_id: str):
    from browser_use import BrowserSession, BrowserProfile, Agent
    from browser_use.llm.google.chat import ChatGoogle
    from custom_actions import controller
    from cache import NavCache

    state.agent_running = True
    cache = NavCache(user_id=user_id)

    # ─── 자격증명 ───
    cred = get_credential(user_id, "cybercampus")
    if not cred:
        await broadcast_chat({
            "type": "error",
            "text": "사이버캠퍼스 비밀번호가 등록되지 않았습니다."
        })
        state.agent_running = False
        return

    # ─── 캐시 조회 ───
    is_first_run = len(cache.cache) == 0
    cached = cache.lookup(task)

    if cached:
        await broadcast_chat({
            "type": "status",
            "text": f"⚡ 캐시 히트: {cached['course']} → {cached['intent']}"
        })
    elif is_first_run:
        await broadcast_chat({
            "type": "status",
            "text": "🔍 일반 탐색 모드 (첫 실행 시 과목 자동 학습)"
        })
    else:
        await broadcast_chat({"type": "status", "text": "🔍 일반 탐색 모드"})

    # ─── LLM & Browser ───
    llm = ChatGoogle(model="gemini-2.5-flash", api_key=GEMINI_API_KEY)
    
    browser = BrowserSession(
        browser_profile=BrowserProfile(
            headless=True,
            keep_alive=True,
            allowed_domains=[
                "dcs-lcms.cnu.ac.kr",
                "dcs-learning.cnu.ac.kr",
                "portal.cnu.ac.kr",
            ],
            wait_for_network_idle_page_load_time=10,
            maximum_wait_page_load_time=30,
        )
    )
    state.browser = browser

    sensitive_data = {
        "dcs-lcms.cnu.ac.kr": {
            "x_user_id": cred["cnu_id"],
            "x_user_pw": cred["cnu_pw"],
        }
    }

    final_task_used_cache = False

    try:
        # ─── 캐시 히트 시: 로그인 → 점프 → 짧은 태스크 ───
        if cached:
            try:
                # 1단계: 로그인만
                login_agent = Agent(
                    task=f"{BASE} 로그인만 해주세요.",
                    llm=llm, browser=browser, controller=controller,
                    use_vision=False,
                    sensitive_data=sensitive_data,
                )
                await broadcast_chat({"type": "status", "text": "🔑 로그인 중..."})
                await login_agent.run(max_steps=8)

                # 2단계: 캐시 점프
                page = await browser.get_current_page()
                if page is not None:
                    jumped = await navigate_to_cached_course(
                        page, cached["course_id"], cached["menu_text"]
                    )
                    if jumped:
                        await broadcast_chat({
                            "type": "status",
                            "text": "🚀 캐시로 점프 성공"
                        })
                        final_task_used_cache = True
                    else:
                        await broadcast_chat({
                            "type": "status",
                            "text": "⚠️ 캐시 점프 실패 → 일반 모드"
                        })

                # 3단계: 짧은 태스크
                if final_task_used_cache:
                    agent = Agent(
                        task=f"현재 페이지에서 다음을 수행하세요: {task}",
                        llm=llm, browser=browser, controller=controller,
                        use_vision=False,
                    )
                    max_steps = 5
                else:
                    # fallback to normal mode
                    agent = Agent(
                        task=f"{BASE} 로그인한 후, {task}",
                        llm=llm, browser=browser, controller=controller,
                        use_vision=False,
                        sensitive_data=sensitive_data,
                    )
                    max_steps = 20
            except Exception as e:
                print(f"[main] cache flow error: {e}")
                # 완전 fallback
                agent = Agent(
                    task=f"{BASE} 로그인한 후, {task}",
                    llm=llm, browser=browser, controller=controller,
                    use_vision=False,
                    sensitive_data=sensitive_data,
                )
                max_steps = 20
        else:
            # ─── 일반 모드 ───
            if "파일" in task and ("업로드" in task or "제출" in task or "첨부" in task):
                full_task = (
                    f"{BASE} 로그인한 후, {task}. "
                    f"파일 첨부 시 반드시 '파일 업로드' 액션을 사용하세요."
                )
            else:
                full_task = f"{BASE} 로그인한 후, {task}"
            
            agent = Agent(
                task=full_task,
                llm=llm, browser=browser, controller=controller,
                use_vision=False,
                sensitive_data=sensitive_data,
            )
            max_steps = 20

        # ─── 에이전트 실행 ───
        history = await agent.run(max_steps=max_steps)
        success = history.is_successful()
        raw_result = history.final_result() or "결과 없음"

        # ─── 후처리: Course Discovery + 캐시 저장 ───
        try:
            page = await browser.get_current_page()
            
            if page is not None:
                # 첫 실행이면 전체 과목 일괄 등록
                if is_first_run:
                    courses = await discover_all_courses(page)
                    if courses:
                        added = cache.record_bulk(courses)
                        if added > 0:
                            await broadcast_chat({
                                "type": "status",
                                "text": f"📚 {added}개 과목 자동 학습 완료"
                            })
                
                # 일반 모드 성공 시 현재 course_id도 저장
                if success and not final_task_used_cache:
                    course_id = await extract_current_course_id(page)
                    if course_id:
                        recorded = cache.record(task, course_id)
                        if recorded:
                            await broadcast_chat({
                                "type": "status",
                                "text": f"💾 캐시 저장: {recorded}"
                            })
        except Exception as e:
            print(f"[main] post-processing error: {e}")

        # ─── 결과 카드 변환 ───
        await broadcast_chat({"type": "status", "text": "📋 결과 정리 중..."})
        card = await format_result_to_card(task, raw_result)

        await broadcast_chat({
            "type": "done",
            "success": success,
            "text": raw_result,
            "card": card,
            "steps": history.number_of_steps(),
            "from_cache": final_task_used_cache,
        })

    except Exception as e:
        print(f"[main] exception: {e}")
        await broadcast_chat({"type": "error", "text": f"에러: {str(e)[:200]}"})
    finally:
        try:
            await browser.stop()
        except:
            pass
        state.browser = None
        state.agent_running = False
# backend/nav_cache.py
import json
import os
import re
import time
from typing import Optional

INTENT_PATTERNS = {
    "공지사항": ["공지사항", "공지", "알림"],
    "과제": ["과제", "숙제"],
    "자료실": ["자료실", "강의자료", "자료"],
    "QnA": ["Q&A", "qna", "질문"],
    "자유게시판": ["자유게시판", "게시판"],
    "강의수강": ["강의수강", "강의보기", "수업"],
    "성적": ["성적", "점수"],
    "출석": ["출석", "출결"],
}

# 페이지 유형 → 좌측 사이드바 메뉴 텍스트
INTENT_TO_MENU_TEXT = {
    "공지사항": "공지사항",
    "과제": "과제",
    "자료실": "자료실",
    "QnA": "Q&A",
    "자유게시판": "자유게시판",
    "강의수강": "강의수강",
    "성적": "성적",
    "출석": "학습현황",
}


class NavCache:
    """
    사이버캠퍼스 SPA 캐시.
    - 과목명 → course_id 매핑 저장
    - 한 번의 로그인으로 myCourseList에서 전체 과목 자동 발견 (Course Discovery)
    """
    CACHE_DIR = "./data/user_cache"

    def __init__(self, user_id: str = "default"):
        self.user_id = user_id
        os.makedirs(self.CACHE_DIR, exist_ok=True)
        self.cache_path = os.path.join(self.CACHE_DIR, f"{user_id}.json")
        self.cache = self._load()
        print(f"[NavCache] user={user_id}, loaded {len(self.cache)} courses")

    def _load(self) -> dict:
        if os.path.exists(self.cache_path):
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[NavCache] load error: {e}")
        return {}

    def _save(self):
        try:
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
            print(f"[NavCache] saved {len(self.cache)} entries")
        except Exception as e:
            print(f"[NavCache] save error: {e}")

    def extract_intent(self, text: str) -> Optional[str]:
        for intent, kws in INTENT_PATTERNS.items():
            for kw in kws:
                if kw in text:
                    return intent
        return None

    def extract_course(self, text: str) -> Optional[str]:
        BLACKLIST = {"이번", "다음", "마감", "오늘", "내일", "주", "월", "일",
                     "최근", "신규", "모든", "전체"}

        # 캐시에 있는 과목명 우선 매칭 (긴 이름부터)
        known = sorted(self.cache.keys(), key=len, reverse=True)
        for course in known:
            if course in text:
                return course
            # 부분 매칭도 시도 (예: "범죄" → "범죄의진실과오해")
            if len(course) >= 4:
                for chunk in [course[:2], course[:3], course[:4]]:
                    if chunk in text and len(chunk) >= 2:
                        return course

        # 휴리스틱 fallback
        intent_words = [w for ws in INTENT_PATTERNS.values() for w in ws]
        for iw in intent_words:
            if iw in text:
                before = text.split(iw)[0].strip()
                before = re.sub(r"(과목|에서|의|을|를|,)", " ", before).strip()
                if before:
                    candidate = before.split()[-1]
                    if candidate not in BLACKLIST and len(candidate) >= 2:
                        return candidate
        return None

    def lookup(self, text: str) -> Optional[dict]:
        course = self.extract_course(text)
        intent = self.extract_intent(text)

        if not course or not intent:
            print(f"[NavCache] lookup FAILED: course={course}, intent={intent}")
            return None

        if course not in self.cache:
            print(f"[NavCache] MISS: '{course}' not in cache")
            return None

        course_data = self.cache[course]
        course_id = course_data.get("course_id")
        if not course_id:
            return None

        menu_text = INTENT_TO_MENU_TEXT.get(intent, intent)
        print(f"[NavCache] HIT: {course} → {course_id}, menu={menu_text}")
        return {
            "course": course,
            "intent": intent,
            "course_id": course_id,
            "menu_text": menu_text,
        }

    def record(self, text: str, course_id: str) -> Optional[str]:
        """단일 과목 등록 (캐시 미스 후 일반 모드로 성공했을 때)"""
        course = self.extract_course(text)
        if not course or not course_id:
            print(f"[NavCache] record SKIP: course={course}, id={course_id}")
            return None

        self.cache[course] = {
            "course_id": course_id,
            "last_accessed": time.time(),
            "access_count": self.cache.get(course, {}).get("access_count", 0) + 1,
        }
        self._save()
        print(f"[NavCache] RECORDED: {course} → {course_id}")
        return course

    def record_bulk(self, course_list) -> int:
        """방어적 일괄 등록"""
        # 문자열로 들어오면 파싱 시도
        if isinstance(course_list, str):
            try:
                course_list = json.loads(course_list)
            except:
                print(f"[NavCache] record_bulk: cannot parse string")
                return 0
        
        if not isinstance(course_list, list):
            print(f"[NavCache] record_bulk: not a list, got {type(course_list)}")
            return 0
        
        added = 0
        for c in course_list:
            if not isinstance(c, dict):
                print(f"[NavCache] skip non-dict: {type(c).__name__}")
                continue
            
            name = c.get("course_nm") or c.get("course_name")
            cid = c.get("course_id") or c.get("courseId")
            
            if not name or not cid:
                continue
            
            if name not in self.cache:
                self.cache[name] = {
                    "course_id": cid,
                    "prof_nm": c.get("prof_nm"),
                    "term_year": c.get("term_year"),
                    "term_cd": c.get("term_cd"),
                    "class_no": c.get("class_no"),
                    "discovered": True,
                    "last_accessed": time.time(),
                    "access_count": 0,
                }
                added += 1
        
        if added > 0:
            self._save()
            print(f"[NavCache] BULK RECORDED: {added} new courses")
        return added
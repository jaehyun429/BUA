# custom_actions.py
from pydantic import BaseModel
from browser_use import Controller
import asyncio

controller = Controller()


class FileUploadParams(BaseModel):
    file_path: str


@controller.action(
    "파일 업로드 (과제/게시판에 파일 첨부)",  # 모델이 이걸 보고 결정
    param_model=FileUploadParams,
)
async def upload_file_custom(params: FileUploadParams, browser):
    """
    사이버캠퍼스 파일 업로드 전체 시퀀스 자동 처리.
    과제 페이지, 게시판 글쓰기에서 파일을 첨부할 때 사용.
    """
    page = await browser.get_current_page()
    
    try:
        # 1. "파일 첨부" 버튼 클릭 — 여러 셀렉터 시도
        attach_selectors = [
            'button:has-text("파일 첨부")',
            'a:has-text("파일 첨부")',
            'button:has-text("파일첨부")',
            '[data-act="fileAttach"]',
            '.btn_file_attach',
        ]
        
        clicked = False
        for sel in attach_selectors:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=1000):
                    await btn.click()
                    clicked = True
                    break
            except:
                continue
        
        if not clicked:
            return "파일 첨부 버튼을 찾을 수 없음"
        
        # 2. 모달 로딩 대기
        await page.wait_for_timeout(1500)
        
        # 3. 숨겨진 input에 직접 파일 설정
        upload_selectors = [
            'input#uploadBox[type="file"]',
            'input[type="file"][name="upload"]',
            '.dropzone input[type="file"]',
            'input[type="file"]',  # 마지막 폴백
        ]
        
        uploaded = False
        for sel in upload_selectors:
            try:
                file_input = page.locator(sel).first
                # is_visible 체크 안 함 (숨겨져 있어도 동작)
                await file_input.set_input_files(params.file_path, timeout=3000)
                uploaded = True
                break
            except:
                continue
        
        if not uploaded:
            return f"파일 input을 찾을 수 없음: {params.file_path}"
        
        # 4. 업로드 진행 대기 (사이버캠퍼스는 즉시 업로드)
        await page.wait_for_timeout(2500)
        
        # 5. 모달 안 "확인/저장" 버튼 클릭
        confirm_selectors = [
            '.modal:visible button:has-text("저장")',
            '.modal:visible button:has-text("확인")',
            '.modal:visible button:has-text("적용")',
            '.modal-footer button.btn-primary',
            'button.dz-confirm',
        ]
        
        for sel in confirm_selectors:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=1000):
                    await btn.click()
                    await page.wait_for_timeout(1500)
                    break
            except:
                continue
        
        return f"파일 업로드 완료: {params.file_path.split('/')[-1]}"
    
    except Exception as e:
        return f"파일 업로드 실패: {str(e)[:200]}"
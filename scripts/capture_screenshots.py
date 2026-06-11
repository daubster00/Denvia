"""Denvia 운영 서버 화면 자동 캡쳐.

운영 서버(https://denvia.ai.kr) 기준 사용자/관리자 화면을 Playwright로 캡쳐.
PII가 보일 수 있는 관리자 화면은 CSS 마스킹을 주입해서 가린다.

산출물:
    outputs/screenshots/user_*.png        — 비로그인/시연 계정 사용자 화면
    outputs/screenshots/admin_*.png       — 마스터 관리자 화면

자격:
    - 시연 계정: demo@denvia.ai.kr / Demo1234! (운영 DB INSERT 완료)
    - 마스터: btmdesign@naver.com / Btm6853!

실행:
    py -3 scripts/capture_screenshots.py [user|admin|all]
"""

from __future__ import annotations

import io
import sys
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

from playwright.sync_api import Page, sync_playwright

BASE = "https://denvia.ai.kr"
SHOT_DIR = Path(__file__).resolve().parent.parent / "outputs" / "screenshots"
SHOT_DIR.mkdir(parents=True, exist_ok=True)

DEMO_EMAIL = "demo@denvia.ai.kr"
DEMO_PASSWORD = "Demo1234!"
ADMIN_EMAIL = "btmdesign@naver.com"
ADMIN_PASSWORD = "Btm6853!"

VIEWPORT = {"width": 1440, "height": 900}


# PII가 보일 수 있는 영역을 흐리게 처리하는 CSS
PII_MASK_CSS = """
/* 회원 검색·상세 등 PII 영역 마스킹 */
[data-pii], .pii-mask {
    filter: blur(8px) !important;
}
/* 이메일 셀 자동 흐림 */
td:has(> *:is(a, span):not(:empty)):where([class*="email"]),
.email-cell, [data-column="email"] {
    filter: blur(6px) !important;
}
/* 휴대폰 패턴 셀 */
td:where([data-column="phone"]) {
    filter: blur(6px) !important;
}
"""


def safe_wait(page: Page) -> None:
    """networkidle 시도, 실패해도 OK (SSE/polling 페이지 대응)."""
    try:
        page.wait_for_load_state("domcontentloaded", timeout=10000)
    except Exception:
        pass
    try:
        page.wait_for_load_state("networkidle", timeout=4000)
    except Exception:
        pass
    time.sleep(1.2)


def shoot(page: Page, name: str, *, full: bool = True) -> None:
    """안정 대기 후 PNG 저장."""
    safe_wait(page)
    out = SHOT_DIR / f"{name}.png"
    page.screenshot(path=str(out), full_page=full)
    print(f"  [OK] {out.name} ({out.stat().st_size // 1024} KB)")


def open_login_popup(page: Page) -> None:
    """랜딩에서 로그인 팝업 띄우기 (여러 진입점 시도)."""
    selectors = [
        'text=로그인',
        'button:has-text("로그인")',
        'a:has-text("로그인")',
        '[data-testid="login-button"]',
    ]
    for sel in selectors:
        try:
            page.locator(sel).first.click(timeout=3000)
            time.sleep(0.5)
            return
        except Exception:
            pass
    print("  ! 로그인 버튼 못 찾음")


def login_user(page: Page, email: str, password: str) -> None:
    """API 로그인으로 세션 쿠키 획득 후 페이지 reload."""
    page.evaluate(
        """async ({email, password}) => {
            const res = await fetch('/api/v1/auth/login', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({email, password}),
                credentials: 'include',
            });
            return res.status;
        }""",
        {"email": email, "password": password},
    )
    time.sleep(0.4)


def login_admin(page: Page) -> None:
    """API 로그인으로 세션 쿠키 획득."""
    page.goto(f"{BASE}/admin/login")
    safe_wait(page)
    status = page.evaluate(
        """async ({email, password}) => {
            const res = await fetch('/api/v1/admin/auth/login', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({email, password}),
                credentials: 'include',
            });
            return res.status;
        }""",
        {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    print(f"  admin login: HTTP {status}")
    time.sleep(0.8)


# ──────────────────────────────────────────────────────────────────────────────
# 사용자 화면 (비로그인 + 시연 계정)
# ──────────────────────────────────────────────────────────────────────────────

def capture_user_screens(page: Page) -> None:
    print("\n[USER] 비로그인 화면")

    # 1. 랜딩
    page.goto(f"{BASE}/")
    shoot(page, "user_01_landing")

    # 2. 로그인 팝업
    page.goto(f"{BASE}/")
    safe_wait(page)
    open_login_popup(page)
    shoot(page, "user_02_login_popup", full=False)

    # 3. 비번 찾기
    try:
        page.locator('text=비밀번호').first.click(timeout=3000)
        time.sleep(0.6)
        shoot(page, "user_03_password_reset", full=False)
    except Exception as e:
        print(f"  ! 비번 찾기 진입 실패: {e}")

    # 4. 비로그인 채팅(랜딩의 채팅창)
    page.goto(f"{BASE}/")
    safe_wait(page)
    try:
        chat_input = page.locator('textarea, input[placeholder*="질문"], input[placeholder*="궁금"]').first
        chat_input.fill("스케일링 보험청구 어떻게 하나요?")
        time.sleep(0.4)
        shoot(page, "user_04_qa_chat_guest", full=False)
    except Exception as e:
        print(f"  ! 채팅 입력 실패: {e}")
        shoot(page, "user_04_qa_chat_guest", full=False)

    # ── 시연 계정 로그인 ──
    print("\n[USER] 시연 계정 로그인 화면")
    page.goto(f"{BASE}/")
    safe_wait(page)
    login_user(page, DEMO_EMAIL, DEMO_PASSWORD)

    # 5. 로그인 후 채팅 화면
    page.goto(f"{BASE}/")
    shoot(page, "user_05_qa_chat_authed")

    # 6. 마이페이지
    for path in ["/my", "/mypage", "/account"]:
        page.goto(f"{BASE}{path}")
        time.sleep(0.4)
        if page.url.endswith(path) or path.strip("/") in page.url:
            break
    shoot(page, "user_06_mypage")

    # 7. 구독 결제
    page.goto(f"{BASE}/subscribe")
    shoot(page, "user_07_subscribe")

    # 8. 받은 쪽지함
    page.goto(f"{BASE}/inbox")
    shoot(page, "user_08_inbox")

    # 9. 1:1 문의
    page.goto(f"{BASE}/my/inquiries")
    shoot(page, "user_09_inquiries")


# ──────────────────────────────────────────────────────────────────────────────
# 관리자 화면 (마스터 로그인 + PII 마스킹)
# ──────────────────────────────────────────────────────────────────────────────

ADMIN_PAGES = [
    # (파일명, 실제 URL, PII 마스킹 여부) — 보고서 관리자 화면 12종과 매핑
    # 모두 mask=True로 통일 (PII 노출 안전성 우선)
    ("admin_01_login",            "/admin/login",                            False),
    ("admin_02_dashboard",        "/admin",                                  True),
    ("admin_03_users_list",       "/admin/users",                            True),
    ("admin_04_users_edits",      "/admin/users/edits",                      True),
    ("admin_05_analytics_signups","/admin/dashboard/analytics/signups",      True),
    ("admin_06_analytics_segments","/admin/dashboard/analytics/segments",    True),
    ("admin_07_finance_revenue",  "/admin/finance/revenue",                  True),
    ("admin_08_rag_data",         "/admin/rag/data",                         True),
    ("admin_09_rag_prompts",      "/admin/rag/prompts",                      True),
    ("admin_10_anomaly",          "/admin/anomaly",                          True),
    ("admin_11_finance_payments", "/admin/finance/payments",                 True),
    ("admin_12_killswitch",       "/admin/finance/killswitch",               True),
    ("admin_13_cs",               "/admin/cs",                               True),
    ("admin_14_popups",           "/admin/content/popups",                   True),
    ("admin_15_settings",         "/admin/settings",                         True),
    ("admin_16_admins",           "/admin/admins",                           True),
    ("admin_17_admins_logs",      "/admin/admins/logs",                      True),
]


def admin_login_via_api(page: Page) -> int:
    """현재 컨텍스트에서 admin 로그인 API 호출. 세션 쿠키 갱신."""
    return page.evaluate(
        """async ({email, password}) => {
            const res = await fetch('/api/v1/admin/auth/login', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({email, password}),
                credentials: 'include',
            });
            return res.status;
        }""",
        {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )


def capture_admin_screens(page: Page) -> None:
    # 1) 로그인 전: 로그인 화면 먼저 캡쳐
    print("\n[ADMIN] 로그인 화면 캡쳐")
    page.goto(f"{BASE}/admin/login")
    shoot(page, "admin_01_login")

    # 2) 로그인 후
    print("\n[ADMIN] 마스터 로그인")
    login_admin(page)

    for name, path, mask in ADMIN_PAGES:
        if name == "admin_01_login":
            continue  # 이미 위에서 캡쳐
        print(f"  → {path}")
        try:
            # 매 페이지 진입 전 세션 갱신 (일부 페이지가 401 redirect 하는 패턴 대응)
            admin_login_via_api(page)
            page.goto(f"{BASE}{path}", timeout=30000)
            safe_wait(page)
            # 로그인 화면이 떴으면 한 번 더 시도
            if "/admin/login" in page.url and path != "/admin/login":
                admin_login_via_api(page)
                page.goto(f"{BASE}{path}", timeout=30000)
                safe_wait(page)
            if mask:
                page.add_style_tag(content=PII_MASK_CSS)
                # 마스터 본인 이메일도 마스킹 (헤더 우상단)
                page.evaluate(
                    f"""(adminEmail) => {{
                      const re = /[\\w.+-]+@[\\w.-]+\\.[\\w-]{{2,}}|01[016-9]-?\\d{{3,4}}-?\\d{{4}}/;
                      document.querySelectorAll('td, span, div, p, a, button').forEach(el => {{
                        if (el.children.length === 0) {{
                          const t = (el.textContent || '').trim();
                          if (re.test(t) || t === adminEmail) {{
                            el.style.filter = 'blur(5px)';
                          }}
                        }}
                      }});
                    }}""",
                    ADMIN_EMAIL,
                )
                time.sleep(0.3)
            shoot(page, name)
        except Exception as e:
            print(f"  ! {name} 실패: {e}")


# ──────────────────────────────────────────────────────────────────────────────
# main
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            viewport=VIEWPORT,
            locale="ko-KR",
            ignore_https_errors=True,
        )
        page = context.new_page()
        page.set_default_timeout(20000)

        try:
            if mode in ("user", "all"):
                capture_user_screens(page)
            if mode in ("admin", "all"):
                # 관리자는 별도 컨텍스트 (사용자 세션과 분리)
                if mode == "all":
                    context.close()
                    context = browser.new_context(
                        viewport=VIEWPORT, locale="ko-KR", ignore_https_errors=True
                    )
                    page = context.new_page()
                    page.set_default_timeout(20000)
                capture_admin_screens(page)
        finally:
            context.close()
            browser.close()

    print(f"\n[DONE] 캡쳐 폴더: {SHOT_DIR}")
    files = sorted(SHOT_DIR.glob("*.png"))
    print(f"총 {len(files)}장")
    for f in files:
        print(f"  - {f.name}")


if __name__ == "__main__":
    main()

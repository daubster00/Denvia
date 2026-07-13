"""Redis DB 3 런타임 기본값 시드 — 멱등 (이미 존재 시 skip).

실행: cd api && uv run python scripts/seed_runtime_config.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import redis

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
REDIS_DB = 3  # RuntimeConfig DB


DEFAULTS = {
    "runtime:prompt_modules": json.dumps(
        {
            "치식_위치": True,
            "치면_방향": True,
            "마취_산정": True,
            "브릿지": True,
        }
    ),
    "runtime:rag_k": "5",
    "runtime:rag_temperature": "0.0",
    # 사용자 질문 입력 글자수 상한 (#85) — 시스템 프롬프트 제외, 순수 질문만 카운트.
    "runtime:max_question_chars": "2000",
    "runtime:show_upgrade_prompt": "true",
    # Story 2.3 — 무료 quota + 의도적 지연 + 구독 버튼 토글
    "runtime:free_daily_quota": "10",
    "runtime:free_delay_enabled": "true",
    "runtime:free_delay": "1",
    "runtime:free_delay_notice_text": "현재는 무료버전으로 답변 출력은 약 40초가량 소요됩니다.",
    "runtime:pro_internal_cap": "500",
    # Pro 구독 상품 — 한 달간 사용 가능한 질문 횟수 (KST 월초 기준 리셋).
    "runtime:pro_monthly_quota": "500",
    "runtime:show_subscribe_button": "true",
    # #130 ① — 질문 전송 시 화면 중앙 안내 팝업 (관리자 콘텐츠>서비스 토글에서 편집).
    "runtime:qa_notice_enabled": "true",
    "runtime:qa_notice_text": (
        "현재 질문하신 내용에 대한 정보만 제공하며 이전에 질문하신 내용을 참고하여 "
        "정보를 제공하지 않습니다. Denvia는 매 질문을 항상 새로운 독립질문으로 처리합니다."
    ),
    "runtime:qa_notice_font_size": "16",
    "runtime:qa_notice_color": "#111111",
    "runtime:qa_notice_font_weight": "500",
    "runtime:qa_notice_width": "420",
    # Story 4.2 — 야간 광고 차단 토글 (협의서 #C-02, NFR-C5)
    # runtime:night_block_active는 Beat가 매일 SET하므로 시드 불필요
    "runtime:night_ad_block_enabled": "true",
    "runtime:night_block_start_hour": "21",
    "runtime:night_block_end_hour": "8",
    # 관리자 설정 — RAG 본 체인 채팅 모델. ADR-0002 §결정 2 인수자 기본값 유지.
    "runtime:chat_model": "o4-mini",
    # 이상 질문 패턴 throttle — 답변 완료 후 3초 이내 후속 질문 연속 3회 시 자동 적용.
    "runtime:anomaly_throttle_enabled": "true",
    "runtime:anomaly_throttle_free_delay": "5.0",
    "runtime:anomaly_throttle_pro_delay": "2.0",
    # 로그인 실패 이상탐지 기준 — N회 연속 실패 시 anomaly + 잠금. 관리자 편집(1~20).
    "runtime:login_brute_threshold": "3",
    # ── 이상탐지 통합 임계값 (/admin/anomaly/thresholds 페이지에서 관리자 편집) ──
    # 1) 비밀번호 반복 실패 — 잠금 지속 시간(초). 기본 600(10분), 60~86400.
    "runtime:login_lockout_seconds": "600",
    # 2) 동일 IP 다중 로그인 — 동시 계정 수 + 윈도우.
    "runtime:concurrent_ip_threshold": "3",
    "runtime:concurrent_ip_window_seconds": "600",
    # 3) 동일 질문 반복.
    "runtime:repeated_question_threshold": "3",
    # 4) 답변 직후 빠른 후속 질문.
    "runtime:rapid_followup_window_seconds": "3.0",
    "runtime:rapid_followup_threshold": "3",
    # 5) 휴대폰 인증 남용.
    "runtime:sms_max_retries": "5",          # 시간당 발송 허용
    "runtime:sms_abuse_threshold": "10",     # 1시간 누적 N회 → 24h 차단
    "runtime:sms_max_wrong": "3",            # OTP 오답 허용
    # 6) 비밀번호·아이디 찾기 남용.
    "runtime:recovery_abuse_threshold": "4",
}


def seed():
    client = redis.from_url(REDIS_URL, db=REDIS_DB, decode_responses=True)
    seeded = 0
    skipped = 0
    for key, value in DEFAULTS.items():
        if client.exists(key):
            print(f"  skip (exists): {key}")
            skipped += 1
        else:
            client.set(key, value)
            print(f"  set: {key}")
            seeded += 1
    print(f"\n✅ 시드 완료 — set {seeded}개, skip {skipped}개")


if __name__ == "__main__":
    seed()

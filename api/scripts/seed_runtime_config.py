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

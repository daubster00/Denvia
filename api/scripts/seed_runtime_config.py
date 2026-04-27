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

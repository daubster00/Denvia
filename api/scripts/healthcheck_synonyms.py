"""Story 8.5 live healthcheck — T22~T25 검증 스크립트.

`uv run python -m api.scripts.healthcheck_synonyms` 로 실행한다.

검증 항목:
- admin login 200
- GET  /admin/rag/synonyms 200 + Cache-Control: no-store
- POST /admin/rag/synonyms 201 (신규 그룹 생성)
- PUT  /admin/rag/synonyms/{id} 200 (수정)
- DELETE /admin/rag/synonyms/{id} 204 (삭제)
- CSV import dry_run 200
- GET  /admin/rag/synonyms/export 200 + text/csv + BOM
- Redis runtime:synonyms_v1 DELETE 발생 확인
"""
from __future__ import annotations

import asyncio
import sys

import httpx

BASE_URL = "http://localhost:8000"
LOGIN = {"email": "admin@denvia.local", "password": "change_me_in_production"}


async def main() -> int:
    failures: list[str] = []

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        # 1) admin login
        r = await client.post("/api/v1/admin/auth/login", json=LOGIN)
        if r.status_code != 200:
            print(f"[FAIL] admin login: {r.status_code} {r.text[:200]}")
            return 1
        print("[PASS] T22 admin login 200")

        # 2) GET list
        r = await client.get("/api/v1/admin/rag/synonyms?size=5")
        if r.status_code != 200:
            failures.append(f"GET list: {r.status_code}")
        elif r.headers.get("cache-control") != "no-store":
            failures.append(f"GET list missing Cache-Control: no-store ({r.headers.get('cache-control')})")
        else:
            body = r.json()
            print(f"[PASS] T22 GET list 200 (total={body['total']}, returned={len(body['groups'])})")

        # 3) POST create
        r = await client.post(
            "/api/v1/admin/rag/synonyms",
            json={"canonical_term": "테스트치아", "synonyms": ["테스트유치", "테스트영구치"]},
        )
        if r.status_code != 201:
            failures.append(f"POST create: {r.status_code} {r.text[:200]}")
            new_id = None
        else:
            new_id = r.json()["id"]
            print(f"[PASS] T23 POST 201 (id={new_id})")

        # 4) PUT update
        if new_id is not None:
            r = await client.put(
                f"/api/v1/admin/rag/synonyms/{new_id}",
                json={"canonical_term": "테스트치아", "synonyms": ["테스트유치"]},
            )
            if r.status_code != 200:
                failures.append(f"PUT update: {r.status_code} {r.text[:200]}")
            else:
                print(f"[PASS] T23 PUT 200")

        # 5) CSV import dry-run
        csv_body = "canonical_term,synonyms\n새대표어1,새동의어1|새동의어2\n새대표어2,새동의어3\n".encode("utf-8")
        files = {"file": ("test.csv", csv_body, "text/csv")}
        r = await client.post(
            "/api/v1/admin/rag/synonyms/import?dry_run=true", files=files
        )
        if r.status_code != 200:
            failures.append(f"CSV dry-run: {r.status_code} {r.text[:200]}")
        else:
            summary = r.json()["summary"]
            print(f"[PASS] T25 CSV dry-run 200 (to_create={summary['to_create']}, conflicts={summary['conflicts']})")

        # 6) export
        r = await client.get("/api/v1/admin/rag/synonyms/export")
        if r.status_code != 200:
            failures.append(f"CSV export: {r.status_code}")
        elif "text/csv" not in r.headers.get("content-type", ""):
            failures.append(f"CSV export content-type: {r.headers.get('content-type')}")
        elif not r.content.startswith(b"\xef\xbb\xbf"):
            failures.append("CSV export missing UTF-8 BOM")
        else:
            print(f"[PASS] T25 GET export 200 + BOM + text/csv ({len(r.content)} bytes)")

        # 7) DELETE
        if new_id is not None:
            r = await client.delete(f"/api/v1/admin/rag/synonyms/{new_id}")
            if r.status_code != 204:
                failures.append(f"DELETE: {r.status_code} {r.text[:200]}")
            else:
                print(f"[PASS] T23 DELETE 204")

        # 8) Redis cache invalidation check
        from redis.asyncio import Redis

        from api.src.services.synonym_service import RUNTIME_CACHE_KEY
        from api.src.settings import REDIS_DB_RUNTIME_CONFIG, settings

        r_redis = Redis.from_url(
            settings.redis_url, db=REDIS_DB_RUNTIME_CONFIG, decode_responses=True
        )
        async with r_redis:
            await r_redis.set(RUNTIME_CACHE_KEY, '{"sentinel":true}', ex=60)
            # 다시 POST create → DELETE 호출되었는지
            r = await client.post(
                "/api/v1/admin/rag/synonyms",
                json={"canonical_term": "캐시테스트", "synonyms": []},
            )
            if r.status_code != 201:
                failures.append("cache-invalidate setup post fail")
            else:
                cache_after = await r_redis.get(RUNTIME_CACHE_KEY)
                if cache_after is None:
                    print("[PASS] T23 Redis cache invalidated on POST create")
                else:
                    failures.append(f"Redis cache NOT invalidated (still: {cache_after[:50]})")
                # cleanup
                await client.delete(f"/api/v1/admin/rag/synonyms/{r.json()['id']}")

        # 9) unauth check
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=5.0) as anon:
            r = await anon.get("/api/v1/admin/rag/synonyms")
            if r.status_code != 401:
                failures.append(f"unauth check: {r.status_code}")
            else:
                print(f"[PASS] T22 unauth 401")

    if failures:
        print(f"\n=== FAILURES ({len(failures)}) ===")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\n=== ALL HEALTHCHECKS PASSED ===")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

"""run_rule_answer가 DB synonyms dict를 실제로 normalize_query에 적용하는지 검증.

vendor/rag 코드는 0줄 수정 — `normalize_query(query, dict)` 시그니처는 그대로 호출하고,
DB(synonym_groups)에서 빌드한 dict를 인자로 직접 전달한다.

Cache-Aside (Redis DB 3) hit / miss 두 경로 모두 검증.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_run_rule_answer_uses_db_dict_when_cache_miss():
    """Redis 캐시 미스 → DB 풀스캔으로 dict 빌드 → Redis SET → normalize_query에 dict 전달."""
    from api.src.rag_integration import query_runner

    # 1) Redis는 miss 반환
    fake_redis = AsyncMock()
    fake_redis.__aenter__ = AsyncMock(return_value=fake_redis)
    fake_redis.__aexit__ = AsyncMock(return_value=False)
    fake_redis.get = AsyncMock(return_value=None)
    fake_redis.set = AsyncMock()

    # 2) DB는 dict 2개 반환
    db_dict = {"광중합기": ["큐링기", "큐어링"], "공단검진": ["국가검진"]}

    # 3) vendor의 normalize_query 호출 캡쳐
    captured_dicts: list[dict] = []

    def fake_normalize_query(query, syn_dict):
        captured_dicts.append(syn_dict)
        return query  # 그대로 통과

    fake_rag = MagicMock()
    fake_rag.apply_scaling_rules = lambda q: q
    fake_rag.normalize_query = fake_normalize_query
    fake_rag.generate_rule_answer = lambda q: f"answer for: {q}"
    fake_rag.init_rag = lambda **kwargs: None

    with (
        patch("redis.asyncio.from_url", return_value=fake_redis),
        patch(
            "api.src.services.synonym_service.build_synonyms_dict_from_db",
            new=AsyncMock(return_value=db_dict),
        ),
        patch.dict(
            "sys.modules",
            {"rag.run_qa": fake_rag},
        ),
        patch.object(query_runner, "_initialized", True),
    ):
        result = await query_runner.run_rule_answer("광중합기 사용법")

    # 정상 동작: normalize_query가 DB dict를 받아서 호출됨
    assert len(captured_dicts) == 1
    assert captured_dicts[0] == db_dict
    assert result == "answer for: 광중합기 사용법"
    # Redis SET 호출 확인
    fake_redis.set.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_rule_answer_uses_cached_dict_on_hit():
    """Redis 캐시 HIT → DB SELECT 없이 캐시된 dict 그대로 사용."""
    import json

    from api.src.rag_integration import query_runner

    cached_dict = {"광중합기": ["큐링기"]}

    fake_redis = AsyncMock()
    fake_redis.__aenter__ = AsyncMock(return_value=fake_redis)
    fake_redis.__aexit__ = AsyncMock(return_value=False)
    fake_redis.get = AsyncMock(return_value=json.dumps(cached_dict, ensure_ascii=False))
    fake_redis.set = AsyncMock()

    captured_dicts: list[dict] = []

    def fake_normalize_query(query, syn_dict):
        captured_dicts.append(syn_dict)
        return query

    fake_rag = MagicMock()
    fake_rag.apply_scaling_rules = lambda q: q
    fake_rag.normalize_query = fake_normalize_query
    fake_rag.generate_rule_answer = lambda q: "ok"
    fake_rag.init_rag = lambda **kwargs: None

    build_mock = AsyncMock()  # DB는 호출되면 안 됨

    with (
        patch("redis.asyncio.from_url", return_value=fake_redis),
        patch(
            "api.src.services.synonym_service.build_synonyms_dict_from_db",
            new=build_mock,
        ),
        patch.dict("sys.modules", {"rag.run_qa": fake_rag}),
        patch.object(query_runner, "_initialized", True),
    ):
        await query_runner.run_rule_answer("질문")

    assert captured_dicts == [cached_dict]
    build_mock.assert_not_awaited()  # DB 우회 확인
    fake_redis.set.assert_not_awaited()  # 캐시 히트 시 SET 안 함


@pytest.mark.asyncio
async def test_run_rule_answer_redis_down_falls_back_to_db():
    """Redis 다운 → DB 풀스캔으로 dict 빌드(매 호출). normalize_query는 정상 호출."""
    from api.src.rag_integration import query_runner

    db_dict = {"광중합기": ["큐링기"]}

    captured_dicts: list[dict] = []

    def fake_normalize_query(query, syn_dict):
        captured_dicts.append(syn_dict)
        return query

    fake_rag = MagicMock()
    fake_rag.apply_scaling_rules = lambda q: q
    fake_rag.normalize_query = fake_normalize_query
    fake_rag.generate_rule_answer = lambda q: "ok"
    fake_rag.init_rag = lambda **kwargs: None

    with (
        patch("redis.asyncio.from_url", side_effect=RuntimeError("redis-down")),
        patch(
            "api.src.services.synonym_service.build_synonyms_dict_from_db",
            new=AsyncMock(return_value=db_dict),
        ),
        patch.dict("sys.modules", {"rag.run_qa": fake_rag}),
        patch.object(query_runner, "_initialized", True),
    ):
        await query_runner.run_rule_answer("질문")

    assert captured_dicts == [db_dict]


@pytest.mark.asyncio
async def test_run_rule_answer_empty_db_falls_back_to_vendor_dict():
    """DB가 비어 있으면 vendor get_syn_dict()를 fallback으로 사용."""
    from api.src.rag_integration import query_runner

    fake_redis = AsyncMock()
    fake_redis.__aenter__ = AsyncMock(return_value=fake_redis)
    fake_redis.__aexit__ = AsyncMock(return_value=False)
    fake_redis.get = AsyncMock(return_value=None)
    fake_redis.set = AsyncMock()

    captured_dicts: list[dict] = []

    def fake_normalize_query(query, syn_dict):
        captured_dicts.append(syn_dict)
        return query

    vendor_dict = {"광중합기": ["큐링기"]}

    fake_rag = MagicMock()
    fake_rag.apply_scaling_rules = lambda q: q
    fake_rag.normalize_query = fake_normalize_query
    fake_rag.generate_rule_answer = lambda q: "ok"
    fake_rag.init_rag = lambda **kwargs: None
    fake_rag.get_syn_dict = lambda: vendor_dict

    with (
        patch("redis.asyncio.from_url", return_value=fake_redis),
        patch(
            "api.src.services.synonym_service.build_synonyms_dict_from_db",
            new=AsyncMock(return_value={}),
        ),
        patch.dict("sys.modules", {"rag.run_qa": fake_rag}),
        patch.object(query_runner, "_initialized", True),
    ):
        await query_runner.run_rule_answer("질문")

    assert captured_dicts == [vendor_dict]

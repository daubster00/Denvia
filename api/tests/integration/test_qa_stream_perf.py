"""SSE Q&A 스트리밍 성능 테스트 — OPENAI_API_KEY 보유 환경에서만 실행.

p50/p95/p99 측정 후 AC-5 임계 검증:
  - 룰 엔진 단락 응답 p95 ≤ 0.5초 (NFR-P1)
  - RAG 전체 응답 p95 ≤ 6초, p99 ≤ 10초 (NFR-P2)
  - 첫 토큰 TTFB p95 ≤ 3초 (NFR-P3)
"""

import os
import statistics
import time

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY 없음 — 성능 테스트 skip",
)

RULE_QUERIES = [
    "장애인 발치 가산 가능한가요?",
    "장애인 근관치료 가산 적용?",
    "장애인 치석제거 가산 되나요?",
]

RAG_QUERIES = [
    "임플란트 보험 적용 기준이 뭔가요?",
    "브릿지 보철물 제거 횟수 계산",
    "침윤마취 전달마취 동시 청구",
    "보험레진 치식 기준",
    "연1회 치석제거 급여 기준",
]


def _percentile(data: list[float], pct: int) -> float:
    data_sorted = sorted(data)
    k = (len(data_sorted) - 1) * pct / 100
    lower = int(k)
    fraction = k - lower
    if lower + 1 < len(data_sorted):
        return data_sorted[lower] + fraction * (data_sorted[lower + 1] - data_sorted[lower])
    return data_sorted[lower]


def _print_stats(label: str, latencies: list[float]) -> None:
    p50 = _percentile(latencies, 50)
    p95 = _percentile(latencies, 95)
    p99 = _percentile(latencies, 99)
    max_lat = max(latencies)
    print(f"\n{'─'*60}")
    print(f"  {label}")
    print(f"  p50={p50*1000:.0f}ms  p95={p95*1000:.0f}ms  p99={p99*1000:.0f}ms  max={max_lat*1000:.0f}ms")
    print(f"{'─'*60}")


@pytest.mark.asyncio
async def test_rule_engine_p95_under_500ms():
    """룰 엔진 단락 응답 p95 ≤ 500ms (NFR-P1)."""
    from api.src.rag_integration import query_runner as qr
    from rag.run_qa import apply_scaling_rules, normalize_query, generate_rule_answer, get_syn_dict

    await qr.ensure_initialized()
    latencies = []

    for q in RULE_QUERIES * 10:
        t0 = time.perf_counter()
        scaled = apply_scaling_rules(q)
        syn = get_syn_dict()
        normalized = normalize_query(scaled, syn)
        _ = generate_rule_answer(normalized)
        latencies.append(time.perf_counter() - t0)

    _print_stats("룰 엔진 단락 응답", latencies)
    p95 = _percentile(latencies, 95)
    assert p95 <= 0.5, f"룰 엔진 p95={p95*1000:.0f}ms > 500ms (NFR-P1 위반)"


@pytest.mark.asyncio
async def test_rag_stream_ttfb_p95_under_3s():
    """RAG 첫 토큰 TTFB p95 ≤ 3초 (NFR-P3)."""
    from api.src.rag_integration import query_runner as qr

    await qr.ensure_initialized()
    ttfb_latencies = []
    total_latencies = []

    for q in RAG_QUERIES * 6:
        ttfb = None
        t0 = time.perf_counter()

        async def _noop(u, full, docs, prompt=None):
            pass

        async for _ in qr.stream_rag_answer(q, _noop):
            if ttfb is None:
                ttfb = time.perf_counter() - t0
            break

        total_latencies.append(time.perf_counter() - t0)
        if ttfb:
            ttfb_latencies.append(ttfb)

    _print_stats("RAG TTFB", ttfb_latencies)
    _print_stats("RAG 전체 응답", total_latencies)

    p95_ttfb = _percentile(ttfb_latencies, 95)
    p95_total = _percentile(total_latencies, 95)
    p99_total = _percentile(total_latencies, 99)

    assert p95_ttfb <= 3.0, f"TTFB p95={p95_ttfb:.2f}s > 3.0s (NFR-P3 위반)"
    assert p95_total <= 6.0, f"전체 p95={p95_total:.2f}s > 6.0s (NFR-P2 위반)"
    assert p99_total <= 10.0, f"전체 p99={p99_total:.2f}s > 10.0s (NFR-P2 위반)"

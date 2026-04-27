# RAG 통합 런북

> **최종 수정일:** 2026-04-27 (Story 2.3: 트래픽 제어 표 §0 추가)
> **작성자:** Hyung woo
> **승인자:** (인수자 검토 시 기입)
> **버전:** v0.1 (§0·§8만)
> **관련 FR/Story:** FR51·FR52·FR53·FR54 / Story 9.5a

---

## 이 문서의 완성 로드맵

본 문서 v0.1은 Story 9.5a에서 **§0(수정 정책) + §8(계약 테스트 가이드)** 만 확정한다. §1~§7 통합 상세는 Story 9.5b(Wave 6, Wave 5 완료 후)에서 v1.0으로 보강 예정이다. Story 2.1(RAG runtime integration) 착수 전 §0만 읽어도 정책 기준을 파악할 수 있도록 §0의 자족성을 보장한다.

---

## §0. 수정 정책

> 참조: [ADR-0002 링크](./adr/0002-rag-integration-contract.md) — 본 섹션의 SSOT.

### 트래픽 제어 표 (Story 2.3 추가)

RAG 호출 이전 단계(preflight)에서 quota·sleep을 제어하는 Redis 키 목록.

| Redis DB | 키 | 설명 | 기본값 |
|---|---|---|---|
| DB 4 | `quota:user:{user_id}:{YYYY-MM-DD(KST)}` | 일일 Q&A INCR 카운터 — TTL 86400s | (없음) |
| DB 3 | `runtime:free_daily_quota` | 무료 사용자 일일 한도 | `10` |
| DB 3 | `runtime:free_delay_enabled` | 무료 지연 전역 ON/OFF | `true` |
| DB 3 | `runtime:free_delay` | 무료 지연 초 | `3` |
| DB 3 | `runtime:pro_internal_cap` | 유료 내부 안전 상한 | `500` |
| DB 3 | `runtime:show_upgrade_prompt` | 구독 유도 토글 | `true` |
| DB 3 | `runtime:show_subscribe_button` | 구독 버튼 노출 토글 | `true` |

### 배경

클라이언트 제공 RAG 코드(`자료/RAG 코드/` → Story 2.1에서 `vendor/rag/`로 이전)는 FastAPI + SSE 웹 서비스와 구조적으로 충돌한다. 2026-04-24 클라이언트 확정 사항: "결과 의도가 보존되는 한 웹 통합 목적 수정 허용."

### 허용 수정 5종 (웹 통합 구조 목적)

| 번호 | 수정 내용 | 목적 |
|---|---|---|
| ① | `while True` CLI 루프 → `if __name__ == "__main__":` 가드 또는 함수형 entry(`answer(query) -> AnswerResult`) 재구성 | HTTP 함수 호출 지원 |
| ② | cwd 상대 경로 → 환경변수/설정 주입(기본값 원본 유지) | Docker 경로 이식성 |
| ③ | 동기 `qa_chain.invoke` → `ChatOpenAI(streaming=True)` + async callback handler로 SSE `event: token` 지원 | 스트리밍 응답 |
| ④ | import 시 즉시 실행 `FAISS.load_local` → lazy init | Worker 시작 지연 방지 |
| ⑤ | 로깅·`trace_id`·structlog·Sentry·OpenAI 토큰·비용 캡처 확장 | 관측성 강화 |

### 금지 수정 4종 (결과 의도 이탈)

| 번호 | 금지 대상 | 이유 |
|---|---|---|
| ① | 동의어 정규화 로직 입출력 매핑 변경 — `apply_scaling_rules`, `normalize_query`, `build_synonym_map`, `_try_synonym_replace`, `_PARTIAL_MATCH_BLACKLIST`, `JOSA` | 클라이언트 확정 도메인 규칙 |
| ② | 장애인가산 룰 엔진 및 사용자 노출 문구 — `PATTERNS`, `DISABILITY_AVAILABLE`, `extract_procedures`, `generate_rule_answer`, `TEMPLATE_OK`, `TEMPLATE_NO`, `TEMPLATE_MULTI` | 클라이언트 확정 도메인 규칙 |
| ③ | 모델·retriever 파라미터 코드 기본값 임의 변경 — `text-embedding-3-large`, `o4-mini`, `k=5` (관리자 A-404 런타임 override는 허용) | 응답 품질 일관성 |
| ④ | 내부 카운트 불일치 임의 수정 — 예: `TEMPLATE_OK` "88개" ↔ `DISABILITY_AVAILABLE` 실제 개수 | 클라이언트가 의도적으로 확정한 문구 |

### 판단 체크리스트 3문항

RAG 코드를 수정하는 PR 작성자와 reviewer 모두 아래 3문항이 **Yes**여야 머지한다.

- ① 동일 입력 → 동일 출력 유지 (텍스트·문서 메타·토큰량 ± 허용 오차)
- ② 동의어 정규화·장애인가산 매칭 결과가 기존과 동일
- ③ 모델·retriever 파라미터 기본값 유지 (`text-embedding-3-large`·`o4-mini`·`k=5`)

---

## §1~§7: RAG 통합 상세 (Story 9.5b 작성 범위)

아래 §1~§7은 **Story 9.5b(Wave 6, Wave 5 완료 후) 작성 범위**다. 본 스토리에서는 제목만 배치한다(2026-04-24 기준 `api/src/rag_integration/` 미존재).

### §1. 인수자 제공 파일 4종 입출력 계약 + 수정 지점 매핑

*(TBD — Story 9.5b)*

### §2. 웹 레이어 통합 지점 (`api/src/rag_integration/`)

*(TBD — Story 9.5b)*

### §3. FAISS 이중 경로 스왑 메커니즘

*(TBD — Story 9.5b)*

### §4. OpenAI 토큰·비용 캡처

*(TBD — Story 9.5b)*

### §5. 프롬프트 블록·모델 파라미터 런타임 반영

*(TBD — Story 9.5b)*

### §6. CI `pathspec-check` 재설정 현황

*(TBD — Story 9.5b)*

### §7. RAG 코드 버전 업그레이드 수용 절차

*(TBD — Story 9.5b)*

---

## §8. 계약 테스트(Contract Tests) 가이드

### 목적

`api/tests/integration/test_rag_contract.py`(Story 2.1에서 생성 예정, 현 시점 미존재)는 "인수자 제공 4종 파일의 입출력 계약이 기존 웹 레이어 통합과 호환"됨을 자동으로 검증하고, §0 판단 체크리스트 3문항을 자동화한다. RAG 코드 수정 PR마다 이 테스트 스위트를 통과해야 한다.

### 실행 방법

```bash
# 로컬
uv --project api run pytest api/tests/integration/test_rag_contract.py -v

# CI (docker-compose)
docker compose -f infra/docker-compose.ci.yml run --rm api pytest api/tests/integration/test_rag_contract.py -v
```

관련 파일 실재: `api/pytest.ini` ✅ · `infra/docker-compose.ci.yml` ✅

### 테스트 케이스 카탈로그 (최소 6종)

- `test_run_qa_signature_stable` — `run_qa.py` 공개 심볼(함수명·인자·반환 타입) 안정성
- `test_prompt_builder_output_shape` — `build_prompt_template(query) -> str` 반환 안정성
- `test_update_vectorstore_idempotent` — 동일 입력 2회 실행 시 인덱스 일치
- `test_faiss_index_read_compat` — 기존 `index_a` 파일을 신규 버전 `run_qa`가 읽을 수 있는지
- `test_synonyms_json_schema` — `config/synonyms.json` 스키마(키·값 타입) 회귀 없음 *(⚠️ 2026-04-24 `자료/RAG 코드/`에 `synonyms.json` 실재 부재 — Story 2.1 착수 전 클라이언트 원본 수령 필요)*
- `test_no_network_in_run_qa` — OpenAI 호출 외 추가 외부 네트워크 호출 없음 (보안·비용 회귀 방지)

### 의도 보존 자동 검증 3항

§0 체크리스트 3문항을 테스트 스위트로 자동화한다. 구현은 Story 2.1에서 진행한다.

1. 동일 입력 → 동일 출력 회귀 테스트 (스냅샷 비교)
2. 동의어 정규화·장애인가산 매칭 결과 회귀 테스트
3. 모델·retriever 파라미터 기본값 assert 테스트

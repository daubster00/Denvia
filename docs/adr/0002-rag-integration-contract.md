# ADR-0002: RAG 통합 계약 — 수정 허용·금지 정책

> **최종 수정일:** 2026-05-20
> **작성자:** Hyung woo
> **승인자:** (인수자 검토 시 기입)
> **버전:** v1.1
> **관련 FR/Story:** FR51·FR52·FR53·FR54 / Story 2.1·8.1·8.3·8.4·9.5a

---

## 상태

Accepted

---

## 맥락

### 인수자 제공 RAG 자산 3파일의 구조적 특징

클라이언트가 제공한 RAG 코드는 `자료/RAG 코드/` 하위 3개 디렉터리에 존재한다.

- `자료/RAG 코드/run_qa/run_qa.py`
- `자료/RAG 코드/prompt_builder/`
- `자료/RAG 코드/update_vectorstore/`

웹 서비스(FastAPI + SSE) 통합을 어렵게 만드는 **구조적 특징 4가지**:

1. **`run_qa.py:544` top-level `while True: input(...)` CLI 루프**
   — `import run_qa` 시 즉시 블로킹 입력 대기 상태가 되어 FastAPI worker를 점유한다.

2. **`run_qa.py:521-527` import 시 `FAISS.load_local` 자동 실행(top-level side effect)**
   — 모듈 import 시 벡터스토어를 즉시 로드한다.
   ```python
   embeddings = OpenAIEmbeddings(model="text-embedding-3-large")
   vectorstore = FAISS.load_local(
       "vectorstore/faiss_index",
       embeddings,
       allow_dangerous_deserialization=True
   )
   retriever = vectorstore.as_retriever(search_kwargs={"k": 5})
   ```

3. **`run_qa.py:583` 동기 `qa_chain.invoke` non-streaming**
   — FastAPI의 SSE 스트리밍 응답(`event: token`)을 지원하지 않는다.
   ```python
   result = qa_chain.invoke({"query": query})
   ```

4. **cwd 상대 경로 하드코딩**
   — `vectorstore/faiss_index`, `config/synonyms.json`, `data/` 경로가 실행 디렉터리에 종속되어 Docker 환경에서 위치를 예측하기 어렵다.

### 웹 서비스 요구사항과의 4개 충돌 지점

| 충돌 지점 | 원본 코드 동작 | FastAPI + SSE 요구사항 |
|---|---|---|
| 실행 방식 | CLI 블로킹 루프 | HTTP 요청-응답 함수 호출 |
| 초기화 시점 | import 즉시 로드 | lazy init (앱 시작 시 또는 첫 요청 시) |
| 응답 방식 | 동기 단일 반환 | async SSE 토큰 스트리밍 |
| 경로 해석 | cwd 상대 경로 | 환경변수 또는 절대 경로 |

### 정책 개정 경위

- **2026-04-21 초기 정책**: "RAG 코드 절대 수정 금지" — `.github/workflows/ci.yml` `pathspec-check` 잡으로 강제 차단 의도.
- **2026-04-24 클라이언트 확정**: "결과 의도가 보존되는 한 웹 통합 목적 RAG 코드 수정 허용"으로 개정.

### CI `pathspec-check` 현황 및 재설정 필요성

현재 `.github/workflows/ci.yml:11-26` `pathspec-check` 잡은 다음 패턴을 사용한다.

```yaml
if echo "$CHANGED" | grep -q "^RAG 코드/"; then
```

그런데 실제 RAG 코드 디렉터리는 `자료/RAG 코드/`이므로 `^RAG 코드/` 패턴과 불일치한다.
**2026-04-24 기준 이 잡은 사실상 no-op 상태 — 어떤 PR도 차단하지 않는다.**

Story 2.1 착수 PR에서 다음 두 작업을 **동시 수행**해야 한다.
- (a) RAG 경로 이전: `자료/RAG 코드/` → `vendor/rag/`
- (b) `pathspec-check` 패턴·가드 로직 재설정: 자동 차단 → 라벨 `rag-modified` + CODEOWNERS 수동 승인

---

## 결정

### 1. 허용 수정 5종 (웹 통합 구조 목적)

| 번호 | 수정 내용 | 목적 |
|---|---|---|
| ① | `while True` CLI 루프 → `if __name__ == "__main__":` 가드 또는 함수형 entry(`answer(query) -> AnswerResult`) 재구성 | HTTP 함수 호출 지원 |
| ② | cwd 상대 경로 → 환경변수/설정 주입(기본값 원본 유지) | Docker 경로 이식성 |
| ③ | 동기 `qa_chain.invoke` → `ChatOpenAI(streaming=True)` + async callback handler로 SSE `event: token` 지원 | 스트리밍 응답 |
| ④ | import 시 즉시 실행 `FAISS.load_local` → lazy init | Worker 시작 지연 방지 |
| ⑤ | 로깅·`trace_id`·structlog·Sentry·OpenAI 토큰·비용 캡처 확장 | 관측성 강화 |

### 2. 금지 수정 4종 (결과 의도 이탈)

| 번호 | 금지 대상 | 이유 |
|---|---|---|
| ① | 동의어 정규화 로직 입출력 매핑 변경 — `apply_scaling_rules`, `normalize_query`, `build_synonym_map`, `_try_synonym_replace`, `_PARTIAL_MATCH_BLACKLIST`, `JOSA` | 클라이언트 확정 도메인 규칙 |
| ② | 장애인가산 룰 엔진 및 사용자 노출 문구 — `PATTERNS`, `DISABILITY_AVAILABLE`, `extract_procedures`, `generate_rule_answer`, `TEMPLATE_OK`, `TEMPLATE_NO`, `TEMPLATE_MULTI` | 클라이언트 확정 도메인 규칙 |
| ③ | 모델·retriever 파라미터 코드 기본값 임의 변경 — `text-embedding-3-large`, `o4-mini`, `k=5` (관리자 A-404 런타임 override는 허용) | 응답 품질 일관성 |
| ④ | "내부 카운트 불일치 개선" 임의 수정 — 예: `TEMPLATE_OK` "88개" ↔ `DISABILITY_AVAILABLE` 실제 개수 불일치 | 클라이언트가 의도적으로 확정한 문구 |

### 3. 판단 체크리스트 3문항

PR 작성자와 reviewer 모두 아래 3문항이 **Yes**여야 머지할 수 있다.

- ① 동일 입력 → 동일 출력 유지 (텍스트·문서 메타·토큰량 ± 허용 오차)
- ② 동의어 정규화·장애인가산 매칭 결과가 기존과 동일
- ③ 모델·retriever 파라미터 기본값 유지 (`text-embedding-3-large`·`o4-mini`·`k=5`)

### 4. 관리자 감사 목적 저장 단서 (v1.1, 2026-05-20)

`return_source_documents` 토글과 동의어 치환 후 쿼리(`normalized_query`)는
**SSE 응답·사용자 노출에 사용하지 않는다**는 원칙은 유지한다. 다만 관리자 페이지
"사용자 → 질의 → 상세보기" 감사 흐름을 위해 다음 저장은 허용한다.

- `qa_logs.normalized_query` (TEXT): `apply_scaling_rules` + `normalize_query` 적용 후 retriever/룰 엔진에 전달된 최종 쿼리.
- `qa_logs.retrieved_docs` (JSONB): top-k 검색 문서들의 `{page_content, metadata}` 직렬화. 본문은 2000자 컷오프.

조건:
- 본 데이터는 **관리자(`require_admin`) 가드 라우터에서만 노출**한다.
- SSE 이벤트(`token`/`done`/`rule_matched`/`reframe`/`error`) 페이로드에는 절대 포함하지 않는다.
- 결과 의도(동일 입력 → 동일 출력)는 변경되지 않는다 — `return_source_documents=True`는 저장만 추가하며, 응답 텍스트·토큰 사용량·매칭 결과에 영향 없음 (체크리스트 3문항 통과 유지).

---

## 근거

### 기억 인용

`memory/project_rag_provided_asset.md` (2026-04-24 개정): "결과 동치성·문구·모델 파라미터 이탈은 금지하되, 웹 통합 목적 구조 수정(CLI 루프·경로 주입·streaming 래핑) 허용."

### 기술 대안 비교

| 옵션 | 접근 방식 | 장점 | 단점 | 채택 |
|---|---|---|---|---|
| A | 심볼만 부분 재사용(importlib/AST) | 원본 코드 0줄 수정 | `while True` top-level 때문에 `import` 자체 불가 → 극단적 해킹 필요, streaming 불가 | ❌ |
| B | 클라이언트에 `if __name__` 가드 1줄 추가 요청 | 최소 변경 | 소유권 혼재(수정 권한 불명확), streaming 별도 필요 | ❌ |
| C | 본 결정 방식(허용 5종/금지 4종/체크리스트 3문항) | 웹 통합에 필요한 모든 수정 가능 + 의도 보존 게이트 존재 | 수정 PR마다 reviewer 판단 필요 | ✅ 선정 |

---

## 영향받는 산출물

- **Story 2.1** — RAG runtime integration: 허용 수정 5종 적용, `vendor/rag/` 경로 이전, `pathspec-check` 재설정
- **Story 8.1·8.3·8.4** — 관리자 RAG: 동일 허용·금지 범위 적용
- **`.github/workflows/ci.yml` `pathspec-check` 재설정** — Story 2.1 착수 PR에서 수행 (현 no-op 교정 포함)
- **`vendor/rag/`** — 신설 경로 (Story 2.1에서 `자료/RAG 코드/` → 이전)
- **`vendor/rag/config/synonyms.json`** — ⚠️ 2026-04-24 `자료/RAG 코드/`에 부재 → 클라이언트 원본 수령 필요, **Story 2.1 블로커**
- **`api/src/rag_integration/`** — 신설 (Story 2.1 ⏳)
- **`api/src/integrations/openai/`** — 신설 (Story 2.1 ⏳)
- **`api/tests/integration/test_rag_contract.py`** — 스냅샷 회귀 테스트, 체크리스트 3문항 자동화 (Story 2.1 ⏳)
- **`docs/RUNBOOK_RAG.md` §0** — 본 ADR과 1:1 정합 운영 문서 (Story 9.5a)

---

## 날짜·승인자

2026-04-24 · 작성자 Hyung woo · 승인자 (인수자 검토 시 기입)

# vendor/rag — 클라이언트 제공 RAG 자산

이 디렉터리는 클라이언트(인수자)가 제공한 RAG 코드를 웹 서비스 통합을 위해 이전한 것입니다.

## 원본 위치

`자료/RAG 코드/` → `vendor/rag/` (Story 2.1 PR에서 이전)

## 수정 정책

**ADR-0002: RAG 통합 계약** (`docs/adr/0002-rag-integration-contract.md`) 를 반드시 숙지하십시오.

### 허용 수정 5종

| 번호 | 내용 |
|------|------|
| ① | `while True` CLI 루프 → `if __name__ == "__main__":` 가드 |
| ② | cwd 상대 경로 → 환경변수/설정 주입(기본값 원본 유지) |
| ③ | 동기 `qa_chain.invoke` → `ChatOpenAI(streaming=True)` + async callback |
| ④ | import 시 즉시 실행 `FAISS.load_local` → lazy init |
| ⑤ | 로깅·trace_id·structlog·Sentry·OpenAI 토큰·비용 캡처 확장 |

### 금지 수정 4종

| 번호 | 내용 |
|------|------|
| ① | 동의어 정규화 로직 입출력 매핑 변경 |
| ② | 장애인가산 룰 엔진 및 사용자 노출 문구 변경 |
| ③ | 모델·retriever 파라미터 기본값 임의 변경 (text-embedding-3-large / o4-mini / k=5) |
| ④ | "내부 카운트 불일치" 임의 수정 |

## PR 머지 전 체크리스트 3문항 (작성자·reviewer 모두 Yes)

- [ ] 동일 입력 → 동일 출력 유지 (텍스트·문서 메타·토큰량 ± 허용 오차)
- [ ] 동의어 정규화·장애인가산 매칭 결과가 기존과 동일
- [ ] 모델·retriever 파라미터 기본값 유지 (`text-embedding-3-large`·`o4-mini`·`k=5`)

<!-- SSOT: docs/CODING_CONVENTIONS.md §6 — 본 템플릿과 동일 문면 유지. §6 변경 시 본 템플릿도 동기 갱신 필수. -->

## 변경 사항 요약
<1~3줄 요약>

## 관련 Story / 이슈
- Story X.Y — <제목> / Closes #NNN

## 체크리스트

- [ ] **① 한글 주석 완료** (NFR-M1 — 함수 docstring · 비자명 분기 · 설정값)
- [ ] **② 감사 로그 대상 확인** (NFR-S7 8종 액션 해당 시 `middleware/audit.py` 기록 포함)
- [ ] **③ 외부 연동 어댑터 경유** (포트-어댑터 — `integrations/<provider>/` 직통 import 금지)
- [ ] **④ Pydantic 스키마 변경 시 zod 동기화 완료** (snake_case SSOT 양방향)
- [ ] **⑤ PII 로그 출력 없음** (`_scrub_pii` 대상 4필드 직접 logger 호출 금지)
- [ ] **⑥ `vendor/rag/` 또는 `자료/RAG 코드/` 경로 변경 없음** (변경 시 아래 ⑨ 섹션 필수)
- [ ] **⑦ SSOT 편차 유발 여부** (해당 시 새 ADR 추가 — `docs/adr/0001-ssot-deviations.md` 참조)
- [ ] **⑧ 레이트 리밋 영향 여부** (신규 엔드포인트 시 `deps/rate_limit.py` 반영)

### ⑨ RAG 수정 시 의도 보존 체크 (ADR-0002 §결정)
RAG 미수정 PR은 이 섹션 N/A:
- [ ] 동일 입력 → 동일 출력 유지 (텍스트·문서 메타·토큰량 ± 허용 오차)
- [ ] 동의어 정규화·장애인가산 매칭 결과가 기존과 동일 (`test_rag_contract.py` 회귀 테스트 통과)
- [ ] 모델·retriever 파라미터 기본값 유지 (`text-embedding-3-large`·`o4-mini`·`k=5`)

## 테스트 방법
<리뷰어가 검증할 명령·엔드포인트·엣지케이스>

## 스크린샷 (UI 변경 시)

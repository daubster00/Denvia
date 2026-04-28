# Denvia 문서 인덱스

> **최종 수정일:** 2026-04-24
> **작성자:** Hyung woo
> **승인자:** (인수자 검토 시 기입)
> **버전:** v1.0-draft-phase1 (Story 9.5b 완료 시 v2로 교체)
> **관련 FR/Story:** Story 9.4·9.5a

---

## 문서 저장 위치 규약

| 경로 | 용도 |
|---|---|
| `_bmad-output/planning-artifacts/` | 설계 산출물 (PRD·Architecture·Epics — 개발자 전용) |
| `docs/` | 인수자 운영 문서 (본 인덱스 기준 전수) |
| `.github/` | GitHub 설정 (PR 템플릿·워크플로우·CODEOWNERS) |

---

## §1. 운영 인수 문서 (Story 9.4 산출물, 실재)

| 제목 | 경로 | 목적 |
|---|---|---|
| 개발 환경 실행 가이드 | [DEVELOPMENT.md](./DEVELOPMENT.md) | Docker 개발 환경·hot reload·Windows/WSL 경로 안내 |
| 운영 매뉴얼 | [OPERATIONS.md](./OPERATIONS.md) | 일상 운영·모니터링·스케줄 작업 |
| 인시던트 런북 | [RUNBOOK_INCIDENT.md](./RUNBOOK_INCIDENT.md) | 장애 대응 절차·에스컬레이션 |
| 온보딩 가이드 | [ONBOARDING.md](./ONBOARDING.md) | 인수자 개발팀 최초 세팅·환경 구성 |
| 보안 가이드 | [SECURITY.md](./SECURITY.md) | TLS·인증·접근 제어·취약점 대응 |
| ADR 인덱스 | [adr/README.md](./adr/README.md) | 아키텍처 결정 기록 목록 |
| ADR-0001 | [adr/0001-ssot-deviations.md](./adr/0001-ssot-deviations.md) | SSOT 편차 4건 (가입유형 권한·세그먼트 통합·아이디 찾기·kill-switch 이원화) |

---

## §2. 기술 레퍼런스 문서 (Story 9.5a·9.5b 산출물)

| 제목 | 경로 | 상태 | 버전 |
|---|---|---|---|
| 아키텍처 개요 | [ARCHITECTURE_OVERVIEW.md](./ARCHITECTURE_OVERVIEW.md) | ✅ Story 9.5a | v1.0 (현 구현 + 계획 구분) |
| 코딩 컨벤션 | [CODING_CONVENTIONS.md](./CODING_CONVENTIONS.md) | ✅ Story 9.5a | v1.0 |
| 배포·CI/CD 런북 | [RUNBOOK_DEPLOY.md](./RUNBOOK_DEPLOY.md) | ✅ Story 9.5a | v1.0 |
| RAG 통합 런북 | [RUNBOOK_RAG.md](./RUNBOOK_RAG.md) | ✅ Story 9.5a (§0·§8만) | v0.1 (§1~§7은 Story 9.5b) |
| ADR-0002 | [adr/0002-rag-integration-contract.md](./adr/0002-rag-integration-contract.md) | ✅ Story 9.5a | v1.0 |
| API 레퍼런스 | API_OVERVIEW.md | **(TBD — Story 9.5b, Wave 6)** | — |

---

## §3. 법적 문서 (Story 9.2 예정)

| 제목 | 경로 | 상태 |
|---|---|---|
| 서비스 이용약관·개인정보처리방침 | `legal/terms.md` | **(TBD — Story 9.2, HOLD-MSG 해제 후)** |

---

## §4. 문서 완성 로드맵

본 README v1.0-draft-phase1은 **Story 9.5a 시점 스냅샷**이다.

| 단계 | 완료 기준 | TBD 해소 항목 |
|---|---|---|
| Story 9.5a (현재) | 정책·컨벤션·배포·아키텍처 문서 | — |
| Story 9.5b (Wave 6) | API_OVERVIEW.md + RUNBOOK_RAG §1~§7 v1.0 보강 | `API_OVERVIEW.md`, `RUNBOOK_RAG.md` §1~§7 |
| Story 9.2 (HOLD-MSG 해제 후) | 이용약관·개인정보처리방침 | `legal/terms.md` |

Story 9.5b 완료 시 본 README는 v2로 교체되어 TBD 항목이 모두 해소된다.

---

## 문서 갱신 원칙 3항

1. **메타 블록 갱신**: 문서 수정 시 최상단 `최종 수정일`·`버전`을 반드시 갱신한다.
2. **변경 이력 누적**: 본 문서에 직접 변경 이력을 기록하지 않고, Git 커밋 메시지를 변경 이력으로 사용한다.
3. **중복 통합**: 동일 내용이 두 문서에 존재하면 SSOT를 지정하고 나머지에서 링크로 위임한다.

---

## Epic 9 완료 체크표

| 범주 | 목표 | 현 달성도 (Story 9.5a 완료 시점) |
|---|---|---|
| ADR 등재 | 핵심 결정 ADR 문서화 | ✅ ADR-0001 (Story 9.4) + ADR-0002 (Story 9.5a) = 2건 |
| 운영 문서 5종 | OPERATIONS·RUNBOOK_INCIDENT·ONBOARDING·SECURITY·adr/README | ✅ Story 9.4 |
| 기술 문서 5종 | ARCHITECTURE_OVERVIEW·CODING_CONVENTIONS·RUNBOOK_DEPLOY·RUNBOOK_RAG·API_OVERVIEW | 🟡 4종 ✅ (9.5a) + API_OVERVIEW ⏳ (9.5b) |
| 이용약관 | `legal/terms.md` | ⏳ Story 9.2 HOLD-MSG |
| seed 관리자 문서화 | `api/scripts/seed_admin.py` 용도 및 ⚠️ 편차 문서화 | ✅ Story 9.4 |
| 환경변수 전수 문서화 | 모든 `.env` 변수 발급처 포함 문서화 | ✅ Story 9.5a RUNBOOK_DEPLOY §7 |

# 알림톡 템플릿 카탈로그 (알리고 콘솔 등록용)

> **이 문서의 목적**
> Denvia에서 사용자/관리자에게 보내는 카카오 **알림톡** 메시지를 한 곳에 모아둔 운영 가이드.
> §3 변수 표기 규칙, §4 매핑 환경변수, §5 발송 시점 표, §9 운영 체크리스트, §10 변경 이력이 항상 최신.
> 본문 상세(§6/§7)는 v4 검수 시점 텍스트가 일부 남아있을 수 있으니, **정확한 발송 본문은 코드(`api/src/integrations/messaging/templates.py`) 또는 알리고 콘솔 캡쳐를 직접 참조**하세요.

> **공급자 결정 (2026-05-07 확정)**
> - 알림톡 + SMS 폴백 모두 **알리고(Aligo)** 사용.
> - 환경변수: `MESSAGING_PROVIDER=aligo`
> - 종전 PRD/아키텍처의 HOLD-MSG / AR35 항목은 본 결정으로 해제됨.

> **SSOT 정책 (2026-05-18 확정)**
> - 본문 SSOT 우선순위: **① 알리고 콘솔 등록본 → ② `templates.py` → ③ 본 문서 §6/§7**.
> - 카카오 알림톡은 알리고에 등록된 본문의 고정 텍스트가 발송 본문과 글자 단위로 매칭될 때만 통과합니다. 따라서 알리고 등록본이 최종 진실.
> - 코드(`templates.py`)는 알리고 등록 캡쳐(17/17)와 글자 단위 정렬 완료 (2026-05-18 커밋).
> - 본 문서 §6/§7의 본문 상세 섹션은 v4 검수 시점 텍스트가 남아있을 수 있으므로 운영 참고 시 코드/알리고 콘솔로 교차 확인.

---

## 1. 사용자에게 보여줄 큰 그림 (비유 설명)

알림톡은 **카카오톡으로 자동 발송되는 안내 문자**입니다. 일반 문자(SMS)와 다른 점:
- 우리 회사 채널 이름이 함께 뜸 → 신뢰감 ↑
- 사전에 등록된 **템플릿(=정해진 문장 틀)**만 보낼 수 있음 → 카카오가 한 글자라도 다르면 거부
- 그래서 모든 메시지는 **미리 등록**해야 하고, 이 문서가 그 등록용 원본 대본입니다.

발송 흐름은 다음과 같습니다:
```
서버에서 발송 요청
  → 알리고로 알림톡 발송 시도
     → 성공: 끝
     → 실패(친구톡 거부 / 번호 막힘 등): 자동으로 일반 SMS로 폴백 발송
```

따라서 **알림톡과 SMS는 같은 내용을 보내도록** 등록해 두어야 합니다(SMS는 90자 제한이 있어 본문이 짧아질 수 있음).

---

## 2. 발송 정책 — 알리고 콘솔에서 카테고리 고를 때 참고

| 분류(앱 내부) | 알리고 등록 시 권장 분류 | 야간(21~08 KST) 발송 | 비고 |
|---|---|---|---|
| `BILLING` (결제) | **정보성** — 서비스 이용/결제 안내 | 즉시 | 결제 결과는 즉시 안내 |
| `SUBSCRIPTION` (구독) | **정보성** — 서비스 이용/결제 안내 | 즉시 | 해지·재개 안내 |
| `SYSTEM` (시스템·관리자) | **정보성** — 회원/계정 안내 | 즉시 | 관리자 운영 알림 |
| `SUPPORT` (고객문의) | **정보성** — 회원/계정 안내 | 즉시 | 답변 도착 안내 |
| `NOTICE` (공지) | **정보성** — 공지/안내 | **다음날 08시까지 보류** | 광고성 분류는 사용 안 함 |

> 알리고 콘솔에서 템플릿을 등록할 때 카카오 비즈니스에 사전 등록된 **카카오톡 채널**과 연결해야 하며, 광고성 분류는 사용하지 않습니다(전부 정보성).

폴백 / 속도제한 / 야간차단 규칙은 코드에 이미 구현되어 있어 콘솔 설정에서 신경 쓸 필요 없습니다(참고: `notification_service.py`).

---

## 3. 템플릿 변수 표기 규칙

| 위치 | 표기 | 예시 |
|---|---|---|
| 우리 코드 | `{변수명}` | `결제 금액: {amount_krw}원` |
| 알리고 콘솔 등록 | **`#{변수명}`** | `결제 금액: #{amount_krw}원` |

알리고/카카오 알림톡은 변수를 **`#{...}`** 형식으로 받습니다. 콘솔에 입력할 때 모든 `{변수}`를 `#{변수}`로 바꿔 주세요. 본 문서의 "**알리고 콘솔 입력 본문**" 칸은 이미 변환된 형태로 적어두었습니다.

---

## 4. 매핑 환경변수

알리고 콘솔에 등록된 17개 알림톡 템플릿의 `tpl_code`(템플릿 코드)를 환경변수로 주입합니다. 2026-05-21 시점 — 17개 중 **16개 카카오 심사 통과**, `notice.generic` 1건만 본문 변경 재심사 대기. `.env` 매핑은 통과분 16개를 주입해 두며, 매핑되지 않은 키(`notice.generic`) 발송 시도는 어댑터가 `AligoConfigError`로 거부합니다(다른 알림톡에는 영향 없음).

```env
ALIMTALK_TEMPLATE_MAP_JSON={"billing.first_charge_success":"UH_9828","billing.retry_failed_1":"UH_9829","billing.retry_failed_2":"UH_9831","billing.retry_failed_3":"UH_9824","billing.refund_success":"UH_9832","subscription.cancel_requested":"UH_9833","subscription.canceled_finalized":"UH_9834","subscription.resumed":"UH_9836","support.reply_received":"UH_9837","system.rag_rebuild_complete":"UH_9841","system.rag_rebuild_failed":"UH_9842","admin.budget_warning.80":"UH_9843","admin.budget_warning.95":"UH_9845","admin.budget_hard_cap_reached":"UH_9846","admin.support_inquiry_created":"UH_9848","admin.anomaly_detected":"UH_9849"}
```

> `notice.generic`만 카카오 재심사 큐에 있어 통과 후 위 JSON에 `"notice.generic":"UH_9838"`을 추가하면 됩니다.

### 등록 매핑표 (2026-05-21 갱신)

| # | 코드 측 template_code | 알리고 등록명 | `tpl_code` | 카카오 심사 |
|---|---|---|---|---|
| 1 | `billing.first_charge_success` | Denvia 첫 구독 결제 완료 | `UH_9828` | ✅ 승인 |
| 2 | `billing.retry_failed_1` | Denvia 결제 실패 안내 1차 | `UH_9829` | ✅ 승인 |
| 3 | `billing.retry_failed_2` | Denvia 결제 실패 안내 2차 | `UH_9831` | ✅ 승인 |
| 4 | `billing.retry_failed_3` | Denvia 결제 최종 실패 안내 | `UH_9824` | ✅ 승인 |
| 5 | `billing.refund_success` | Denvia 환불 처리 완료 | `UH_9832` | ✅ 승인 |
| 6 | `subscription.cancel_requested` | Denvia 구독 해지 예약 완료 | `UH_9833` | ✅ 승인 |
| 7 | `subscription.canceled_finalized` | Denvia 구독 해지 완료 | `UH_9834` | ✅ 승인 |
| 8 | `subscription.resumed` | Denvia 구독 해지 철회 완료 | `UH_9836` | ✅ 승인 |
| 9 | `support.reply_received` | Denvia 고객문의 답변 도착 | `UH_9837` | ✅ 승인 |
| 10 | `notice.generic` | Denvia 공지사항 안내 | `UH_9838` | 🟡 본문 변경 → 재심사 대기 |
| 11 | `system.rag_rebuild_complete` | Denvia RAG 재빌드 완료 | `UH_9841` | ✅ 승인 (2026-05-21) |
| 12 | `system.rag_rebuild_failed` | Denvia RAG 재빌드 실패 | `UH_9842` | ✅ 승인 (2026-05-21) |
| 13 | `admin.budget_warning.80` | Denvia 월 예산 80% 도달 | `UH_9843` | ✅ 승인 (2026-05-21) |
| 14 | `admin.budget_warning.95` | Denvia 월 예산 95% 도달 안내 | `UH_9845` | ✅ 승인 (2026-05-21) |
| 15 | `admin.budget_hard_cap_reached` | Denvia 월 예산 소진 안내 | `UH_9846` | ✅ 승인 (2026-05-21) |
| 16 | `admin.support_inquiry_created` | Denvia 신규 1:1 문의 접수 알림 | `UH_9848` | ✅ 승인 |
| 17 | `admin.anomaly_detected` | Denvia 이상탐지 관리자 알림 | `UH_9849` | ✅ 승인 |

> **별도 미등록 — Story 9.1 운영 환불용 알림톡 (2026-05-20 확인)**: 사용자 청약철회는 위 #5 `billing.refund_success`(UH_9832) 단일 템플릿로 통합 운영하지만, 관리자 페이지(Story 9.1) 운영 환불 발송용 별도 템플릿은 현재 알리고 콘솔에 등록되어 있지 않습니다. 향후 운영 환불 본문이 청약철회와 분리될 경우 별도 템플릿 등록 후 본 표에 18번으로 추가.

> **폐기 4건** — `billing.refund_denied`(2026-05-12), `billing.auto_renew_success` / `billing.retry_success` / `subscription.extended_due_to_killswitch`(2026-05-18). 알리고 콘솔에 등록하지 않으며, 위 환경변수 매핑에도 키를 포함하지 마세요. 카탈로그/회귀 가드: `templates.py` + `test_messaging_templates.py` DEPRECATED_TEMPLATE_CODES.

---

## 5. 발송 시점 한눈에 보기

| # | 카테고리 | 템플릿 코드 | 언제 발송되나 | 수신자 | 구현 상태 |
|---|---|---|---|---|---|
| 1 | 결제 | `billing.first_charge_success` | Pro 구독 첫 결제 성공 직후 | 사용자 | ✅ 코드 반영 (v4 본문 수정 2026-05-18) |
| 2 | ~~결제~~ | ~~`billing.auto_renew_success`~~ | ~~매월 자동결제 성공 직후~~ | ~~사용자~~ | **❌ 폐기 — 2026-05-18 (고객 검수 v4)** — 카탈로그·호출처 제거 |
| 3 | ~~결제~~ | ~~`billing.retry_success`~~ | ~~결제 실패 후 재시도가 성공했을 때~~ | ~~사용자~~ | **❌ 폐기 — 2026-05-18 (고객 검수 v4)** — 카탈로그·호출처 제거 |
| 4 | 결제 | `billing.retry_failed_1` | 1차 결제 실패 (1일 뒤 재시도 예정) | 사용자 | ✅ 코드 반영 (v4 본문 수정 2026-05-18) |
| 5 | 결제 | `billing.retry_failed_2` | 2차 결제 실패 (3일 뒤 마지막 재시도) | 사용자 | ✅ 코드 반영 (v4 본문 수정 2026-05-18) |
| 6 | 결제 | `billing.retry_failed_3` | 3차(최종) 결제 실패 — 구독 해지 예정 | 사용자 | ✅ 코드 반영 (v4 본문 수정 2026-05-18) |
| 7 | 결제 | `billing.refund_success` | 환불 처리 완료 시 — ① 사용자 청약철회(즉시 해지 + 전액 환불) 단일. 운영(관리자) 환불용 별도 알림톡은 알리고 미등록 (2026-05-20). | 사용자 | ✅ Story 3.6 v1.1 Patch-T9 코드 반영 (청약철회 발송 연결 완료, UH_9832 승인) · 🟡 Story 9.1 운영 환불용 별도 템플릿 등록 대기 |
| 8 | ~~결제~~ | ~~`billing.refund_denied`~~ | ~~관리자가 수동 환불 요청을 거부했을 때~~ | ~~사용자~~ | **❌ 폐기 — 2026-05-12 (ADR-0001 편차 #5)** — "거부" 개념 자체가 없어짐. 새 정책에서 관리자는 환불을 안 하면 그만(별도 거부 액션 부재) |
| 9 | 구독 | `subscription.cancel_requested` | 사용자가 해지 신청 → 다음 결제일 전까지 유효 | 사용자 | ✅ 코드 반영 (v4 본문 수정 + 무료 전환 안내 2026-05-18) |
| 10 | 구독 | `subscription.canceled_finalized` | 해지 예정일 도달 → 실제로 해지된 시점 | 사용자 | ✅ 코드 반영 (v4 본문 수정 + `user_name`/`effective_at` 신규 변수 2026-05-18) |
| 11 | 구독 | `subscription.resumed` | 해지 예약을 사용자가 다시 철회했을 때 | 사용자 | ✅ 코드 반영 (v4 본문 간결화 + `next_charge_at` 변수 제거 2026-05-18) |
| 12 | 고객문의 | `support.reply_received` | 관리자가 고객문의에 답변을 등록했을 때 | 사용자 | ✅ 코드 반영 + Story 9.3 admin reply 발송 연결 완료 (UH_9837 승인) |
| 13 | 공지 | `notice.generic` | 관리자가 공지 푸시 발송했을 때 | 사용자 | ✅ 코드 반영 · 🟡 본문 변경 → 카카오 재심사 대기 (2026-05-21 시점 유일한 미통과 템플릿) — 매핑 부재로 발송 시도 시 `AligoConfigError` |
| 14 | 시스템 | `system.rag_rebuild_complete` | RAG 지식베이스 재빌드가 완료됐을 때 | 관리자 | ✅ 코드 반영 + 발송 연결 완료 (UH_9841 승인, 2026-05-21) — `workers/rag_tasks.py` `_send_rebuild_notification` |
| 15 | 시스템 | `system.rag_rebuild_failed` | RAG 재빌드가 실패했을 때 | 관리자 | ✅ 코드 반영 + 발송 연결 완료 (UH_9842 승인, 2026-05-21) — `workers/rag_tasks.py` `_send_rebuild_notification` |
| 16 | 시스템 | `admin.budget_warning.80` | 월 OpenAI 비용이 예산의 80% 도달 | 관리자 | ✅ 코드 반영 + 발송 연결 완료 (UH_9843 승인, 2026-05-21) — `workers/budget_tasks.py` (StubMessagingAdapter → get_adapter 교체) |
| 17 | 시스템 | `admin.budget_warning.95` | 월 OpenAI 비용이 예산의 95% 도달 | 관리자 | ✅ 코드 반영 + 발송 연결 완료 (UH_9845 승인, 2026-05-21) — `workers/budget_tasks.py` |
| 18 | 시스템 | `admin.budget_hard_cap_reached` | 월 예산 100% 소진 → 무료 질의 자동 차단 | 관리자 | ✅ 코드 반영 + 발송 연결 완료 (UH_9846 승인, 2026-05-21) — `workers/budget_tasks.py` |
| 19 | 시스템 | `admin.support_inquiry_created` | 사용자가 1:1 문의를 등록한 직후 | 관리자 | ✅ 코드 반영 + 발송 연결 완료 (UH_9848 승인, 2026-05-20) — `routers/support.py` background_tasks |
| 20 | 시스템 | `admin.anomaly_detected` | 이상탐지(비밀번호 다회 오류·동시 로그인·답변 직후 연속 질의·계정 복구 다회 시도 등) 발생 시 | 관리자 | ✅ 코드 반영 + 발송 연결 완료 (UH_9849 승인, 2026-05-20) — `anomaly_service.schedule_admin_anomaly_alimtalk` (login_brute_force / concurrent_ip_login / rapid_followup_questions / recovery_abuse 4종 트리거 · repeated_question 은 enum 정의만, 트리거 미구현) |
| 21 | ~~구독~~ | ~~`subscription.extended_due_to_killswitch`~~ | ~~킬스위치 발동으로 구독 기간 자동 연장됐을 때~~ | ~~사용자~~ | **❌ 폐기 — 2026-05-18** — 클라이언트 v4 검수서(Google Docs 2026-05-15) 미포함. 카탈로그·호출처·docs 본문 섹션 제거. 킬스위치 시 구독 기간 연장 자체는 유지하되 사용자 안내는 인앱 공지·1:1 쪽지로 대체 |

> SMS OTP(회원가입·아이디찾기·비밀번호찾기 인증번호 발송)와 임시 비밀번호 발송은 **알림톡이 아니라 일반 SMS**로 보냅니다. 알리고 콘솔에서는 별도 템플릿 등록이 필요 없습니다(SMS는 자유 텍스트). 본 문서 제일 아래 §8에 정리합니다.

---

## 6. 사용자 발송 템플릿 (등록 대상)

각 항목은 알리고 콘솔에 그대로 옮겨 적으면 됩니다.

---

### 1) `billing.first_charge_success` — 첫 구독 결제 완료 (v4 — 2026-05-18 본문 수정)

- **언제**: 사용자가 Pro 구독을 처음 시작하면서 첫 결제가 성공한 직후
- **수신자**: 결제한 사용자
- **알리고 분류**: 정보성 / 서비스 이용 안내
- **야간 발송**: 즉시
- **알리고 tpl_code**: `_______________` (등록 후 기입)

**제목**
```
첫 구독 결제 완료
```

**알리고 콘솔 입력 본문**
```
안녕하세요, Denvia입니다.
결제가 정상적으로 완료되어 Pro 구독이 시작되었습니다.
문의사항은 앱 내 "문의작성"을 통해 언제든 문의해주세요.
감사합니다.
```

**변수**: 없음 (2026-05-18 v4 — `amount_krw`·`next_charge_at` 변수 제거. 결제 금액·다음 결제일은 본문에 포함하지 않음 — 마이페이지 결제 내역에서 확인.)

**발송 예시**
```
안녕하세요, Denvia입니다.
결제가 정상적으로 완료되어 Pro 구독이 시작되었습니다.
문의사항은 앱 내 "문의작성"을 통해 언제든 문의해주세요.
감사합니다.
```

---

### 2) ~~`billing.auto_renew_success`~~ — 구독 자동 갱신 완료 [❌ 폐기 — 2026-05-18 (고객 검수 v4)]

> ⚠ **본 템플릿은 고객 검수 v4(2026-05-18)에서 "삭제 요청"으로 회신되어 폐기되었습니다.** 자동 갱신 성공 시점에는 사용자에게 알림톡을 발송하지 않습니다.
>
> **알리고 콘솔 등록 대응**:
> - 이미 등록된 경우: 알리고 콘솔에서 본 템플릿을 **비활성/삭제** 처리. `tpl_code` 매핑(`ALIMTALK_TEMPLATE_MAP_JSON`)에서도 제거.
> - 아직 등록 안 한 경우: 등록하지 마세요.
>
> **코드 대응**: `api/src/integrations/messaging/templates.py`에서 카탈로그 항목 제거 완료. `api/src/services/billing_service.py`의 `_notify_renewal()` 호출도 제거 완료(2026-05-18).
>
> 아래 v1.0 본문은 감사 추적 목적으로 보존합니다.

#### v1.0 본문 (감사 보존)

**알리고 콘솔 입력 본문**
```
Denvia Pro 구독이 자동 갱신되었습니다.
결제 금액: #{amount_krw}원
다음 결제일: #{next_charge_at}
```

---

### 3) ~~`billing.retry_success`~~ — 결제 재시도 성공 [❌ 폐기 — 2026-05-18 (고객 검수 v4)]

> ⚠ **본 템플릿은 고객 검수 v4(2026-05-18)에서 "삭제 요청"으로 회신되어 폐기되었습니다.** 결제 재시도 성공 시점에는 사용자에게 알림톡을 발송하지 않습니다.
>
> **알리고 콘솔 등록 대응**: 위 #2와 동일하게 비활성/삭제 처리.
>
> **코드 대응**: `templates.py` 카탈로그 제거 + `billing_service.py` `retry_payment()` 내부의 `_notify_retry(template_code="billing.retry_success", ...)` 호출 블록 제거(2026-05-18).
>
> 아래 v1.0 본문은 감사 추적 목적으로 보존합니다.

#### v1.0 본문 (감사 보존)

**알리고 콘솔 입력 본문**
```
Denvia 구독 결제가 재시도 후 성공했습니다.
결제 금액: #{amount_krw}원
다음 결제일: #{next_charge_at}
```

---

### 4) `billing.retry_failed_1` — 결제 실패 안내 (1차) (v4 — 2026-05-18 본문 수정)

- **언제**: 자동결제 첫 실패 직후 (1일 뒤 재시도 예정)
- **수신자**: 결제 실패한 사용자
- **알리고 분류**: 정보성 / 서비스 이용 안내
- **야간 발송**: 즉시
- **알리고 tpl_code**: `_______________`

**제목**
```
결제 실패 안내 (1차)
```

**알리고 콘솔 입력 본문**
```
안녕하세요 Denvia 입니다.
pro 구독 정기결제에 실패했습니다.
1일 후 자동 재시도됩니다.
카드 정보를 확인해주세요.
```

**변수**: 없음

---

### 5) `billing.retry_failed_2` — 결제 실패 안내 (2차) (v4 — 2026-05-18 본문 수정)

- **언제**: 1차 재시도까지 실패 → 마지막 재시도 3일 전 안내
- **수신자**: 결제 실패한 사용자
- **알리고 분류**: 정보성 / 서비스 이용 안내
- **야간 발송**: 즉시
- **알리고 tpl_code**: `_______________`

**제목**
```
결제 실패 안내 (2차)
```

**알리고 콘솔 입력 본문**
```
Denvia 구독 결제가 다시 실패했습니다.
3일 후 마지막으로 재시도됩니다.
3일 후 결제 실패가 일어나는 경우 pro 구독은 자동 해지될 수 있습니다.
문의사항은 앱 내 "문의작성"을 통해 언제든 문의해주세요.
감사합니다.
```

**변수**: 없음

---

### 6) `billing.retry_failed_3` — 결제 최종 실패 (v4 — 2026-05-18 본문 수정)

- **언제**: 3번째(최종) 재시도까지 모두 실패 → 구독 해지 예정 안내
- **수신자**: 결제 실패한 사용자
- **알리고 분류**: 정보성 / 서비스 이용 안내
- **야간 발송**: 즉시
- **알리고 tpl_code**: `_______________`

**제목**
```
결제 최종 실패
```

**알리고 콘솔 입력 본문**
```
pro 구독 결제가 최종 실패했습니다.
pro구독이 해지될 예정입니다.
고객센터 문의: #{support_url}
```

**변수**

| 변수 | 의미 | 예시 |
|---|---|---|
| `support_url` | 고객센터/문의하기 페이지 URL | `https://denvia.kr/support` |

> 알리고 콘솔에서 **버튼**(웹링크 이동) 추가 옵션을 함께 활성화하면 사용자 클릭률이 높아집니다. 버튼 라벨 권장: `고객센터 바로가기`

---

### 7) `billing.refund_success` — 환불 처리 완료 (v1.1 — 2026-05-12 변수 확장)

- **언제**: 다음 3가지 경우에 동일 템플릿으로 발송 (변수 `refund_reason_label`로 구분)
  - ① **청약철회**: 사용자가 마이페이지 구독 취소 동선 안에서 "즉시 해지 + 전액 환불" 선택 (결제 후 7일 이내 & 질문 0건 충족 시)
  - ② **관리자 수동 전액 환불**: 관리자가 결제내역에서 결제 원금 전액을 환불 처리 (`cancel_amount == amount_krw`)
  - ③ **관리자 수동 부분 환불**: 관리자가 결제내역에서 결제 원금 일부만 환불 처리 (`cancel_amount < amount_krw`)
- **수신자**: 환불 받은 사용자
- **알리고 분류**: 정보성 / 서비스 이용 안내
- **야간 발송**: 즉시
- **알리고 tpl_code**: `_______________`
- **멱등성 키 (코드 측)**:
  - 청약철회: `refund:{payment_id}:cooling_off`
  - 관리자 수동: `refund:{payment_id}:manual:{refund_sequence}` (동일 결제 다회 부분환불 누적 지원)

**제목**
```
환불 처리 완료
```

**알리고 콘솔 입력 본문**
```
환불이 완료되었습니다.
처리 유형: #{refund_reason_label}
결제 원금: #{amount_krw}원
환불 금액: #{refund_amount_krw}원
처리일: #{effective_at}

영업일 3~4일 내 결제 카드로 입금됩니다.
문의는 Denvia 1:1 문의 게시판을 이용해주세요.
```

**변수**

| 변수 | 의미 | 예시 |
|---|---|---|
| `refund_reason_label` | 환불 유형 한국어 표시 (3종 중 하나) | `즉시 해지 및 전액 환불` / `전액 환불` / `부분 환불` |
| `amount_krw` | **결제 원금** (사용자가 결제했던 금액, 콤마 포함) | `30,000` |
| `refund_amount_krw` | **이번에 환불된 금액** (콤마 포함) — 부분환불 시 누적 합이 아니라 이번 처리분만 | `19,000` |
| `effective_at` | 환불 처리일 (KST, "YYYY년 MM월 DD일") | `2026년 5월 12일` |

**`refund_reason_label` 매핑** (코드 측 `refund_reason` enum → 알림톡 본문 표시):

| 코드 측 `refund_reason` | `refund_reason_label` (본문 표시) | 발송 트리거 |
|---|---|---|
| `cooling_off` | `즉시 해지 및 전액 환불` | Story 3.6 v1.1 `cancel-with-refund` |
| `manual_full` | `전액 환불` | Story 9.1 v1.1 관리자 환불 — `cancel_amount == amount_krw` |
| `manual_partial` | `부분 환불` | Story 9.1 v1.1 관리자 환불 — `cancel_amount < amount_krw` |

**발송 예시 (3종)**

*① 청약철회*
```
환불이 완료되었습니다.
처리 유형: 즉시 해지 및 전액 환불
결제 원금: 30,000원
환불 금액: 30,000원
처리일: 2026년 5월 5일

영업일 3~4일 내 결제 카드로 입금됩니다.
문의는 Denvia 1:1 문의 게시판을 이용해주세요.
```

*② 관리자 수동 전액*
```
환불이 완료되었습니다.
처리 유형: 전액 환불
결제 원금: 30,000원
환불 금액: 30,000원
처리일: 2026년 5월 12일

영업일 3~4일 내 결제 카드로 입금됩니다.
문의는 Denvia 1:1 문의 게시판을 이용해주세요.
```

*③ 관리자 수동 부분 (남은 일수만큼 일할 환불)*
```
환불이 완료되었습니다.
처리 유형: 부분 환불
결제 원금: 30,000원
환불 금액: 19,000원
처리일: 2026년 5월 12일

영업일 3~4일 내 결제 카드로 입금됩니다.
문의는 Denvia 1:1 문의 게시판을 이용해주세요.
```

> **카카오 검수 주의** — `refund_reason_label`이 본문 안에 변수로 들어가지만, 라벨 자체가 카카오 광고성 표현(예: 할인·이벤트·축하 등)을 포함하지 않으므로 정보성 검수 통과 가능. 등록 시 위 3가지 라벨 예시를 함께 첨부 권장.

---

### 8) `billing.refund_denied` — 환불 요청 거부 안내 [❌ 폐기 — 2026-05-12 (ADR-0001 편차 #5)]

> ⚠ **본 템플릿은 v1.1 정책 변경으로 폐기되었습니다.** 새 정책(`memory/project_refund_policy.md`)에서 환불 거부 개념 자체가 사라졌습니다. 관리자는 환불을 처리하지 않으면 그만이며, 사용자에게 별도 "거부" 알림을 보내지 않습니다. 환불을 받지 못한 사용자는 1:1 문의 게시판(`inquiry_type=billing`)에서 직접 관리자와 소통합니다.
>
> **알리고 콘솔 등록 대응**:
> - 이미 등록된 경우: 알리고 콘솔에서 본 템플릿을 **비활성/삭제** 처리. `tpl_code` 매핑(`ALIMTALK_TEMPLATE_MAP_JSON`)에서도 제거.
> - 아직 등록 안 한 경우: 등록하지 마세요.
>
> 아래 v1.0 본문은 감사 추적 목적으로 보존합니다.

#### v1.0 본문 (감사 보존)

- **언제**: 관리자가 수동 환불 요청을 거부했을 때
- **수신자**: 환불 요청한 사용자
- **알리고 분류**: 정보성 / 서비스 이용 안내
- **야간 발송**: 즉시
- **알리고 tpl_code**: `_______________`

**제목**
```
환불 요청 거부 안내
```

**알리고 콘솔 입력 본문**
```
환불 요청이 거부되었습니다.
사유 요약: #{reason_summary}
자세한 안내는 쪽지함을 확인해주세요.
```

**변수**

| 변수 | 의미 | 예시 |
|---|---|---|
| `reason_summary` | 거부 사유 한 줄 요약 (관리자가 입력) | `결제 후 30일 경과` |

---

### 9) `subscription.cancel_requested` — 구독 해지 예약 완료 (v4 — 2026-05-18 본문 수정)

- **언제**: 사용자가 마이페이지에서 해지 신청한 직후 (즉시 해지가 아니라 다음 결제일 전까지 사용 가능)
- **수신자**: 해지 신청한 사용자
- **알리고 분류**: 정보성 / 서비스 이용 안내
- **야간 발송**: 즉시
- **알리고 tpl_code**: `_______________`

**제목**
```
구독 해지 예약 완료
```

**알리고 콘솔 입력 본문**
```
Pro 구독 해지가 예약되었습니다.
#{effective_at}까지 pro구독 서비스를 이용하실 수 있으며 이후 무료버전으로 전환됩니다.
감사합니다.
```

**변수**

| 변수 | 의미 | 예시 |
|---|---|---|
| `effective_at` | 해지 효력 발생일 (= 다음 결제 예정일, YYYY-MM-DD) | `2026-06-15` |

---

### 10) `subscription.canceled_finalized` — 구독 해지 완료 (v4 — 2026-05-18 본문 수정 + 변수 신규)

- **언제**: 해지 예정일에 도달해 실제로 구독이 종료된 시점
- **수신자**: 해지된 사용자
- **알리고 분류**: 정보성 / 서비스 이용 안내
- **야간 발송**: 즉시
- **알리고 tpl_code**: `_______________`

**제목**
```
구독 해지 완료
```

**알리고 콘솔 입력 본문**
```
Denvia Pro 구독이 해지되었습니다.
#{user_name} 님은 #{effective_at} 일 부터 무료버전으로 전환 됩니다.
감사합니다.
```

**변수**

| 변수 | 의미 | 예시 |
|---|---|---|
| `user_name` | 사용자 표시 이름 (User 모델에 별도 컬럼이 없어 email local-part로 자동 fallback) | `pro_user` |
| `effective_at` | 무료 전환 효력 발생일 (YYYY-MM-DD) | `2026-02-13` |

> **`user_name` 자동 주입** — `billing_service._notify_subscription_event()`가 호출 측이 `user_name`을 생략한 경우 `user.email.split("@")[0]`(없으면 `"고객"`)을 자동으로 채웁니다. 향후 User 모델에 표시 이름 컬럼이 추가되면 그쪽을 우선 사용하도록 fallback을 갱신하세요.

---

### 11) `subscription.resumed` — 구독 해지 철회 완료 (v4 — 2026-05-18 본문 간결화)

- **언제**: 해지 예약 상태에서 사용자가 "해지 취소"를 누른 직후
- **수신자**: 해지 철회한 사용자
- **알리고 분류**: 정보성 / 서비스 이용 안내
- **야간 발송**: 즉시
- **알리고 tpl_code**: `_______________`

**제목**
```
구독 해지 철회 완료
```

**알리고 콘솔 입력 본문**
```
Pro 구독 해지가 철회되었습니다.
```

**변수**: 없음 (2026-05-18 v4 — `next_charge_at` 변수 제거. 다음 결제일은 마이페이지에서 확인.)

---

### 12) `support.reply_received` — 고객문의 답변 도착 (v4 — 2026-05-18 본문 수정)

- **언제**: 관리자가 사용자의 1:1 문의에 답변을 등록한 직후
- **수신자**: 문의를 작성한 사용자
- **알리고 분류**: 정보성 / 회원·계정 안내
- **야간 발송**: 즉시
- **알리고 tpl_code**: `_______________`

**제목**
```
고객문의 답변이 도착했습니다
```

**알리고 콘솔 입력 본문**
```
안녕하세요. Denvia 입니다.
고객문의에 답변이 등록되었습니다.
문의 제목: #{inquiry_subject}
쪽지함에서 자세한 내용을 확인해주세요.
```

**변수**

| 변수 | 의미 | 예시 |
|---|---|---|
| `inquiry_subject` | 사용자가 작성한 문의 제목 | `결제가 이중으로 빠진 것 같아요` |

> 알리고 콘솔에서 **버튼** 추가 권장 — 라벨: `쪽지함 바로가기`, 링크: `https://denvia.kr/inbox`

---

### 13) `notice.generic` — 일반 공지사항

- **언제**: 관리자가 공지 푸시를 활성화하고 발송 버튼을 눌렀을 때
- **수신자**: 대상 사용자(전체 / 등급별 / 세그먼트별)
- **알리고 분류**: 정보성 / 공지·안내
- **야간 발송**: **차단됨 — 21~08 KST에는 발송하지 않고 다음날 08:00에 묶어서 발송**
- **알리고 tpl_code**: `_______________`

**제목**
```
Denvia 공지사항
```

**알리고 콘솔 입력 본문**
```
#{title}

#{body}
```

**변수**

| 변수 | 의미 | 예시 |
|---|---|---|
| `title` | 공지 제목 | `점검 안내` |
| `body` | 공지 본문 (개행 포함 가능) | `5월 10일 02:00~03:00 점검이 진행됩니다.` |

> 본문 길이가 다양해서 본 템플릿은 카카오 검수에서 까다로울 수 있습니다 — 등록 시 "**광고성**이 아닌 **정보성**"임을 강조하고, 예시 본문을 함께 첨부해 주세요.

---

## 7. 관리자 발송 템플릿 (등록 대상)

이 템플릿들은 **관리자(운영자) 본인의 휴대폰**으로 발송됩니다. 사용자에게는 가지 않습니다. 수신 번호는 환경변수 `DENVIA_ADMIN_PHONE`에 설정.

---

### 14) `system.rag_rebuild_complete` — RAG 재빌드 완료

- **언제**: 관리자 페이지에서 RAG(지식베이스) 재빌드를 실행해 정상 완료된 직후
- **수신자**: 관리자
- **알리고 분류**: 정보성 / 회원·계정 안내
- **야간 발송**: 즉시
- **알리고 tpl_code**: `_______________`

**제목**
```
RAG 재빌드 완료
```

**알리고 콘솔 입력 본문**
```
Denvia RAG 재빌드가 완료되었습니다.
활성 청크 수: #{chunk_count}
```

**변수**

| 변수 | 의미 | 예시 |
|---|---|---|
| `chunk_count` | 새로 활성화된 지식 조각 수 (정수) | `1247` |

---

### 15) `system.rag_rebuild_failed` — RAG 재빌드 실패

- **언제**: 관리자가 시작한 RAG 재빌드가 도중에 실패했을 때
- **수신자**: 관리자
- **알리고 분류**: 정보성 / 회원·계정 안내
- **야간 발송**: 즉시
- **알리고 tpl_code**: `_______________`

**제목**
```
RAG 재빌드 실패
```

**알리고 콘솔 입력 본문**
```
Denvia RAG 재빌드가 실패했습니다.
오류: #{error}
```

**변수**

| 변수 | 의미 | 예시 |
|---|---|---|
| `error` | 실패 원인 한 줄 요약 | `OpenAI API 시간 초과` |

---

### 16) `admin.budget_warning.80` — 월 예산 80% 도달

- **언제**: 이번 달 OpenAI API 사용액이 월 예산의 80%를 처음 넘겼을 때 (한 달에 한 번만)
- **수신자**: 관리자
- **알리고 분류**: 정보성 / 회원·계정 안내
- **야간 발송**: 즉시
- **알리고 tpl_code**: `UH_9843` (✅ 카카오 심사 통과, 2026-05-21)

**제목**
```
[Denvia] 월 예산 80% 도달
```

**알리고 콘솔 입력 본문**
```
이번 달 OpenAI API 비용이 월 예산의 #{percent}%에 도달했습니다.
현재 사용액: #{spent_krw}
월 한도: #{limit_krw}
관리자 대시보드에서 사용 패턴을 점검해주세요.
```

**변수**

| 변수 | 의미 | 예시 |
|---|---|---|
| `percent` | 현재 사용 비율 (정수, 보통 80) | `82` |
| `spent_krw` | 이번 달 사용액(KRW, "₩" prefix + 천단위 콤마 포함된 텍스트) | `₩115,220` |
| `limit_krw` | 월 한도(KRW, "₩" prefix + 천단위 콤마 포함된 텍스트) | `₩140,000` |

---

### 17) `admin.budget_warning.95` — 월 예산 95% 도달 (경고)

- **언제**: 이번 달 사용액이 월 예산의 95%를 처음 넘겼을 때 (한 달에 한 번만)
- **수신자**: 관리자
- **알리고 분류**: 정보성 / 회원·계정 안내
- **야간 발송**: 즉시
- **알리고 tpl_code**: `UH_9845` (✅ 카카오 심사 통과, 2026-05-21)

**제목**
```
[Denvia] 월 예산 95% 도달 — 경고
```

**알리고 콘솔 입력 본문**
```
이번 달 OpenAI API 비용이 월 예산의 #{percent}%에 도달했습니다.
100% 도달 시 무료 질의가 자동 차단됩니다.
현재 사용액: #{spent_krw} / #{limit_krw}
```

**변수**

| 변수 | 의미 | 예시 |
|---|---|---|
| `percent` | 현재 사용 비율 (정수, 보통 95) | `96` |
| `spent_krw` | 이번 달 사용액(KRW, 텍스트) | `₩134,540` |
| `limit_krw` | 월 한도(KRW, 텍스트) | `₩140,000` |

---

### 18) `admin.budget_hard_cap_reached` — 월 예산 100% 소진 (자동 차단)

- **언제**: 이번 달 사용액이 월 예산을 모두 소진해 무료 사용자 질의가 자동 차단된 시점
- **수신자**: 관리자
- **알리고 분류**: 정보성 / 회원·계정 안내
- **야간 발송**: 즉시
- **알리고 tpl_code**: `UH_9846` (✅ 카카오 심사 통과, 2026-05-21)

**제목**
```
[Denvia] 월 예산 소진 — 무료 질의 자동 차단
```

**알리고 콘솔 입력 본문**
```
월 예산 #{limit_krw}이 소진되어 무료 사용자 질의가 일시 차단되었습니다.
유료 사용자는 영향 없습니다.
다음 달 1일 자동 해제 또는 예산 상향 시 즉시 재개됩니다.
```

**변수**

| 변수 | 의미 | 예시 |
|---|---|---|
| `limit_krw` | 월 한도(KRW, 텍스트) | `₩140,000` |

> **재등록 정정 (2026-05-20)**: 초기 KRW 통일 작업 시 16/17/18 재등록 + 카카오 재심사가 필요한 것으로 안내했으나, 실제로는 본문의 `#{spent_usd}` → `#{spent_krw}` 등 **변수명만 바뀌고 등록 본문은 그대로**여서 재등록 불필요로 확인됐습니다.
>
> **심사 통과 (2026-05-21)**: 16/17/18 카카오 심사 모두 통과. `ALIMTALK_TEMPLATE_MAP_JSON`에 `UH_9843`/`UH_9845`/`UH_9846` 매핑이 주입되었고, `workers/budget_tasks.py` 가 `StubMessagingAdapter` → `get_adapter()` 로 교체되어 실제 알리고로 발송됩니다.

---

### 19) `admin.support_inquiry_created` — 신규 1:1 문의 접수 알림

- **언제**: 사용자가 1:1 문의를 등록한 직후
- **수신자**: 관리자 (수신 번호: `DENVIA_ADMIN_PHONE`)
- **알리고 분류**: 정보성 / 회원·계정 안내
- **야간 발송**: 즉시 (운영 알림)
- **알리고 tpl_code**: `UH_9848` (✅ 카카오 심사 통과)
- **구현 상태**: ✅ 코드 반영 + 발송 연결 완료 (2026-05-20). `routers/support.py` 의 `submit_inquiry` 응답 직후 `background_tasks` 로 `_notify_admin_inquiry_created` 실행 → `admin_recipient.resolve_admin_target` 으로 관리자 단일 휴대폰 resolve → `notification_service.send`. 멱등 키 `support_inquiry:{inquiry_id}:admin_alert`.

**제목**
```
[Denvia] 새 1:1 문의 접수
```

**알리고 콘솔 입력 본문**
```
새 1:1 문의가 접수되었습니다.
작성자: #{user_name}
문의 제목: #{inquiry_subject}
관리자 페이지에서 답변을 처리해주세요.
```

**변수**

| 변수 | 의미 | 예시 |
|---|---|---|
| `user_name` | 문의 작성자 표시 이름 (없으면 이메일 앞부분 등 대체) | `홍길동` |
| `inquiry_subject` | 사용자가 작성한 문의 제목 | `결제가 이중으로 빠진 것 같아요` |

> 알리고 콘솔에서 **버튼** 추가 권장 — 라벨: `관리자 페이지 바로가기`, 링크: `https://denvia.kr/admin/cs`
>
> 향후 발송 연결 시 멱등 키 권장: `support:inquiry:{inquiry_id}:created` (중복 발송 방지).

---

### 20) `admin.anomaly_detected` — 이상탐지 발생 알림 (관리자) (신규 — 2026-05-18 v4)

- **언제**: 사용자 계정에서 이상탐지가 감지된 직후 (비밀번호 3회 오류 / 동시 로그인 / 동일 질문 반복 / 답변 출력 후 3초 이내 연속 질문 / 중복 IP 등 모든 이상탐지 패턴)
- **수신자**: 관리자 (수신 번호: `DENVIA_ADMIN_PHONE`)
- **무료/유료 구분**: 없음 — 무료·유료 사용자 모두 동일하게 관리자에게 알림 발송
- **사용자 측 알림톡**: 발송 안 함 (고객 v4 검수 추가요청 — 사용자에게는 카톡 전송 X). 차단 조치 시 사용자 안내는 인앱 1:1 쪽지 + 차단 페이지 팝업으로 별도 전달.
- **알리고 분류**: 정보성 / 회원·계정 안내
- **야간 발송**: 즉시 (운영 알림)
- **알리고 tpl_code**: `UH_9849` (✅ 카카오 심사 통과)
- **구현 상태**: ✅ 코드 반영 + 발송 연결 완료 (2026-05-20). `services/anomaly_service.py` 의 `schedule_admin_anomaly_alimtalk()` 헬퍼가 `asyncio.create_task` 로 fire-and-forget 예약. 트리거 4종 연결:
  - `login_brute_force` ([api/src/services/auth_service.py](../api/src/services/auth_service.py)) — 비밀번호 다회 오류 (oauth_only_hint 변형 + 일반 변형 2개 분기)
  - `recovery_abuse` ([api/src/services/auth_service.py](../api/src/services/auth_service.py)) — 계정 복구(find-id/find-password) 다회 시도
  - `concurrent_ip_login` ([api/src/services/anomaly_service.py](../api/src/services/anomaly_service.py)) — 동일 IP 다수 계정 동시 로그인
  - `rapid_followup_questions` ([api/src/services/anomaly_service.py](../api/src/services/anomaly_service.py)) — 답변 직후 3초 이내 연속 질의
  - `repeated_question` — enum 정의만 존재. 탐지 로직 미구현 (Story 6.2 후속).
  멱등 키 `anomaly:{anomaly_event_id}` — 동일 이벤트 재발송 차단.

**제목**
```
[Denvia] 이상탐지 발생
```

**알리고 콘솔 입력 본문**
```
이상탐지내용: #{anomaly_type}
이상탐지 계정: #{user_identifier}
관리자 페이지에서 확인 필요합니다.
```

**변수**

| 변수 | 의미 | 예시 |
|---|---|---|
| `anomaly_type` | 한국어 사유 라벨 | `비밀번호 3회 오류` / `동시 로그인` / `동일 질문 반복` / `IP 중복` |
| `user_identifier` | 대상 계정 식별자 (email 또는 user_id) | `user@example.com` (또는 `42`) |

> **운영 플로우** — ① 이상탐지 발견 → ② 관리자 알림톡 발송 → ③ 운영자 관리자 페이지 로그인 후 기록 확인 → ④ 조치(해제 / 차단). 차단·정지 시 사용자에게는 1:1 쪽지 + 차단 페이지 팝업으로 사유 안내. 별 문제없으면 아무 행위 없이 종료.
>
> 알리고 콘솔에서 **버튼** 추가 권장 — 라벨: `관리자 페이지 바로가기`, 링크: `https://denvia.kr/admin/anomaly`
>
> 향후 발송 연결 시 멱등 키 권장: `anomaly:{user_id}:{anomaly_type}:{detected_at_unix}` (중복 발송 방지).

---

## 8. 일반 SMS (알림톡 템플릿 등록 불필요)

다음 두 가지는 **일반 SMS**로 보내며 알리고 콘솔에 별도 템플릿 등록이 필요 없습니다(자유 텍스트). 참고용으로 본문 형태만 정리합니다.

### S-1) SMS 인증번호 발송 (회원가입 / 아이디찾기)

- **트리거**: 회원가입·아이디찾기·비밀번호찾기 화면에서 "인증번호 받기" 클릭
- **재발송 제한**: 60초 쿨다운, 시간당 최대 3회
- **본문 예시**
```
[Denvia] 인증번호: 482917
3분 안에 입력해주세요.
```

### S-2) 임시 비밀번호 발송 (비밀번호찾기)

- **트리거**: 비밀번호찾기에서 이메일 + 휴대폰 번호 일치 확인 직후
- **본문 예시**
```
[Denvia] 임시 비밀번호: A7b2K9pX
로그인 후 즉시 변경해주세요.
```

> 두 SMS 모두 단순 텍스트로 발송되며, OTP 자체는 서버 Redis에 보관됩니다(코드/임시비밀번호는 메시지에만 한 번 노출).

---

## 9. 운영 체크리스트 — 알리고 콘솔 등록 순서

1. **카카오 비즈니스 채널** 등록 및 알리고와 연결 (1회성)
2. **발신 번호** 등록 및 인증 (관리자 휴대폰, 1회성)
3. 본 문서의 §6, §7에 있는 **19개 템플릿**을 차례로 등록
   - 각 템플릿마다 발급되는 `tpl_code`를 본 문서의 "**알리고 tpl_code**" 칸에 기입
   - 카카오 검수 통과까지 통상 1~2영업일 소요
4. 모든 등록이 끝나면 `tpl_code`를 모아 환경변수 작성:
   ```
   ALIMTALK_TEMPLATE_MAP_JSON={"billing.first_charge_success":"...","billing.auto_renew_success":"...", ...}
   ```
5. 백엔드 환경변수 갱신:
   ```
   MESSAGING_PROVIDER=aligo
   ALIGO_API_KEY=...                  # 알리고 마이페이지에서 발급
   ALIGO_USER_ID=...                  # 알리고 가입 ID
   ALIGO_SENDER=01012345678           # 알리고에 사전 인증된 발신번호
   ALIGO_SENDER_KEY=...               # 카카오 채널 인증 후 알리고가 발급한 송신프로필키
   ALIGO_TEST_MODE=true               # 가입 직후/스테이징은 true (실제 발송 안 됨, 과금 없음)
   ALIMTALK_TEMPLATE_MAP_JSON={"billing.first_charge_success":"TX_001", ...}
   DENVIA_ADMIN_PHONE=010-...
   ```
6. 스테이징에서 `ALIGO_TEST_MODE=true`로 어댑터가 정상 호출되는지 확인 → 각 템플릿당 1건씩 검증
7. 프로덕션 배포 시 `ALIGO_TEST_MODE=false` 로 전환

> **개발자 주의**: `ALIGO_TEST_MODE=true` 일 때도 알리고는 정상 응답(`result_code=1`, `code=0`)을 돌려주지만 실제 카카오톡/문자는 발송되지 않습니다. 키 검증·연결성 테스트용. 발송 검증은 반드시 `false` 로 전환한 뒤 실수신자(개발자 본인 번호)로 시범 발송하세요.

---

## 10. 변경 이력

| 일자 | 변경 내용 |
|---|---|
| 2026-05-07 | 최초 작성. 알리고 공급자 확정(AR35 / HOLD-MSG 해제). 18개 템플릿(알림톡 16 + SMS 2) 카탈로그화. |
| 2026-05-12 | #19 `admin.support_inquiry_created` 추가 — 사용자가 1:1 문의를 등록한 직후 관리자에게 알림톡. 코드 카탈로그(`templates.py`)에 템플릿 정의만 반영, 라우터 발송 연결은 Story 9.3 후속 작업으로 분리. |
| 2026-05-12 | **환불 정책 재편 반영 (ADR-0001 편차 #5).** ① #7 `billing.refund_success` 변수 확장 — `amount_krw`(기존, 의미 명확화: 결제 원금) + `refund_amount_krw`(신규, 이번 환불 금액) + `refund_reason_label`(신규, "즉시 해지 및 전액 환불" / "전액 환불" / "부분 환불") + `effective_at`(기존, 형식 "YYYY년 MM월 DD일"). 본문도 4줄 → 6줄로 확장하여 처리 유형·결제 원금·환불 금액을 구분 표시. 청약철회·관리자 전액·관리자 부분 3가지 트리거를 단일 템플릿으로 통합. ② #8 `billing.refund_denied` **폐기** — 새 정책에서 환불 "거부" 개념 자체가 사라짐. 알리고 콘솔 등록분이 있다면 비활성/삭제 처리. ③ 발송 시점 표(§5)도 동일하게 갱신. **알리고 콘솔 재등록 필요** — #7 본문 변경분은 카카오 사전 승인 재요청 필수. 코드 측 `templates.py` 갱신은 Story 3.6 v1.1 Patch-T9 + Story 9.1 v1.1 Patch-T8에서 동시 진행. |
| 2026-05-18 | **고객 검수 v4 회신 반영.** ① **폐기 2건**: #2 `billing.auto_renew_success`(자동 갱신 알림) + #3 `billing.retry_success`(재시도 성공 알림) — 카탈로그·호출처(`billing_service._notify_renewal` 및 retry_success 발송 블록)·관련 단위 테스트 정리. ② **본문 수정 7건**: #1 first_charge_success / #4 retry_failed_1 / #5 retry_failed_2 / #6 retry_failed_3 / #9 cancel_requested / #10 canceled_finalized / #11 resumed / #12 support.reply_received — 인사말 추가·무료 전환 안내 보강·변수 정리. ③ **변수 변경**: #10 `canceled_finalized` → `user_name`(email local-part fallback) + `effective_at` 신규. #11 `resumed` → `next_charge_at` 변수 제거. #1 `first_charge_success` → 변수 0개로 단순화. ④ **신규 #20 `admin.anomaly_detected`** — 이상탐지(비밀번호 오류·동시 로그인·동일 질문 반복·IP 중복 등) 발생 시 관리자에게만 발송. 사용자에게는 알림톡 미발송(차단 조치 시 1:1 쪽지+팝업으로 별도 전달). 무료/유료 동일. 발송 연결은 Story 6.2 후속. ⑤ **이상탐지 사용자 알림 5종 미도입**: 본 검수에서 사용자 알림(계정 잠금·답변 속도 제한·동시 로그인·반복 질문·이용 제한 해제) 5건은 모두 삭제 요청으로 정리되어 카탈로그에 등록하지 않음. **알리고 콘솔 재등록 필요** — 본문 수정 7건 모두 카카오 사전 승인 재요청 필수. |
| 2026-05-18 (오후) | **알리고 등록본 SSOT 정렬.** 알리고 콘솔에 17개 알림톡 등록 완료(카카오 심사 진행 중) → 등록 캡쳐 17/17과 코드 `templates.py` 본문 대조 결과 16개에서 차이 발견(인사말·대소문자 Pro/pro·띄어쓰기·본문 첫 줄 [Denvia] 제목 중복·`$` 기호 위치). 알리고 등록본을 SSOT로 채택하고 코드 본문을 등록본으로 정렬. ① `templates.py` 17개 본문 재작성(알리고 캡쳐 글자 단위 일치) — `first_charge_success`는 알리고 v1(변수 2개: `amount_krw`/`next_charge_at`)로 복원, `retry_failed_3`은 `support_url` 변수 제거(콘솔 웹링크 버튼 대체), 관리자 5건은 본문 첫 줄 `[Denvia]` 제목 중복 포함. ② `subscription.extended_due_to_killswitch` **폐기** — 클라이언트 v4 검수서에 미포함. 카탈로그·`billing_service.py` 호출 라인·`unused 변수` 제거. ③ `budget_tasks.py` 호출처 `spent_usd`/`limit_usd`에 `$` prefix 추가(코드 본문에서 `$` 제거 대응). ④ §4 매핑 환경변수에 tpl_code 17개 채워넣음(UH_9824 ~ UH_9849). ⑤ `test_messaging_templates.py` DEPRECATED 회귀가드에 `subscription.extended_due_to_killswitch`·`billing.refund_denied` 추가. **알리고 콘솔 재등록 불필요** — 코드만 알리고에 맞춤. |
| 2026-05-20 | **전체 시스템 통화 표기 KRW 통일.** 관리자 예산 경고 3종(#16 `admin.budget_warning.80` / #17 `admin.budget_warning.95` / #18 `admin.budget_hard_cap_reached`) 본문에서 USD 표기를 KRW로 변경. ① **변수명 교체**: `spent_usd` → `spent_krw`, `limit_usd` → `limit_krw`. ② **본문**: `$#{spent_usd}` → `#{spent_krw}` (값에 "₩" prefix + 천단위 콤마가 포함된 형태로 호출처에서 넘김, 예: `₩115,220`). ③ **호출처 변경**: `budget_tasks.py`에서 USD 값에 `runtime:usd_to_krw` 환율을 곱해 KRW 정수로 변환 후 텍스트로 포맷. ④ **API 응답**: `/admin/budget/current-month`, `/admin/killswitch/status`, `/admin/analytics/user-tokens` 응답에 `monthly_limit_krw` / `spent_krw` / `usd_to_krw` 등 KRW 환산 보조 필드 추가 (DB 컬럼은 USD 유지). ⑤ **UI**: 관리자 대시보드·매출·Kill-switch·설정·사용자 토큰 화면에서 `$` 표기 전면 제거 → `₩` + `toLocaleString("ko-KR")` 통일. ⑥ **테스트**: backend/frontend 관련 모킹 데이터 갱신. ~~알리고 콘솔 재등록 + 카카오 비즈니스 재심사 필수~~ → **2026-05-20 (오후) 재정정**: 변수명만 바뀌고 등록 본문은 그대로여서 재등록 불필요로 확인됨. 검수중인 #16/17/18 통과 즉시 발송 가능. |
| 2026-05-21 | **`rapid_questions` 탐지 프로세스 완전 폐기.** ① `anomaly_service.check_rapid_questions` 함수·`ANOMALY_TYPES` 상수·`_ANOMALY_TYPE_LABEL_KO` 라벨에서 `rapid_questions` 제거. ② `anomaly_event_type` Postgres enum 에서도 값 제거(마이그레이션 0047) + 잔존 anomaly_events 행 DELETE. ③ `admin.anomaly_detected` 본문은 변동 없음(트리거 4종에 `rapid_followup_questions` 가 그대로 자리. **재등록 불필요**). 배경: `rapid_followup_questions`(답변 직후 3초 연속) 와 성격이 중복돼 2026-05-21 부로 hook 호출은 이미 비활성화 상태였음. 본 변경은 잔존 코드/데이터 정리. |
| 2026-05-21 | **카카오 심사 잔여 5건 통과 + 예산 알림톡 실어댑터 전환.** ① **추가 통과 5건** — UH_9841 (system.rag_rebuild_complete) / UH_9842 (system.rag_rebuild_failed) / UH_9843 (admin.budget_warning.80) / UH_9845 (admin.budget_warning.95) / UH_9846 (admin.budget_hard_cap_reached). 17개 중 16개 통과, `notice.generic`(UH_9838) 본문 변경 재심사 1건만 잔여. ② **`ALIMTALK_TEMPLATE_MAP_JSON` 16개 매핑 주입** — `.env` 73행 갱신 (11→16). ③ **`workers/budget_tasks.py` 실어댑터 전환** — `_build_notification_service`가 `StubMessagingAdapter()` 직접 인스턴스화하던 부분을 `get_adapter()`로 교체. `MESSAGING_PROVIDER=aligo` 환경에서 80%/95%/100% 임계 알림톡이 실제 알리고로 발송됨. `rag_tasks.py`는 이미 `get_notification_service()`를 사용하고 있어 매핑 추가만으로 즉시 발송 가능. ④ `.env.example` / `.env.production.example` 매핑 안내 주석 16/17 갱신. |
| 2026-05-20 (오후) | **알리고 카카오 심사 일부 통과 + 관리자 알림톡 발송 연결 완료.** ① **카카오 심사 통과 11건** — UH_9828 / UH_9829 / UH_9831 / UH_9824 / UH_9832 / UH_9833 / UH_9834 / UH_9836 / UH_9837 / **UH_9848** (admin.support_inquiry_created) / **UH_9849** (admin.anomaly_detected). 검수중 6건 — notice.generic(본문 변경 → 재심사) / system.rag_rebuild_complete·failed / admin.budget_warning.80·95 / admin.budget_hard_cap_reached. ② **`ALIMTALK_TEMPLATE_MAP_JSON` 11개 매핑 주입** — `.env` 73행 갱신. 검수 통과되지 않은 6개는 매핑 부재로 어댑터가 `AligoConfigError` 거부 → 다른 알림톡에 영향 없음. ③ **#19 admin.support_inquiry_created 발송 연결** — `routers/support.py` 의 `submit_inquiry` 직후 `background_tasks` 로 `_notify_admin_inquiry_created` 실행. 관리자 단일 발송 (`integrations/messaging/admin_recipient.resolve_admin_target` 신규 헬퍼). 멱등 키 `support_inquiry:{inquiry_id}:admin_alert`. ④ **#20 admin.anomaly_detected 발송 연결** — `services/anomaly_service.schedule_admin_anomaly_alimtalk()` 헬퍼 추가 (asyncio.create_task fire-and-forget). 트리거 4종 wire-up: `login_brute_force`(auth_service 2곳) · `recovery_abuse`(auth_service) · `concurrent_ip_login` · `rapid_questions` (anomaly_service). `repeated_question` enum 정의만 — 탐지 로직 미구현 (Story 6.2 후속). 멱등 키 `anomaly:{anomaly_event_id}`. ⑤ **카카오 심사 정정** — 16/17/18 KRW 통일은 재등록 불필요로 확인. notice.generic 만 본문 변경 → 재심사 대기. ⑥ **Story 9.1 운영 환불용 별도 알림톡** — 알리고 콘솔 미등록. 향후 운영 환불 본문이 청약철회와 분리될 경우 별도 18번 템플릿으로 등록 예정. |

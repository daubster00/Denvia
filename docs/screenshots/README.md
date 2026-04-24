# Screenshots — 인수 데모 시 교체

본 디렉터리는 `docs/ONBOARDING.md` Step 1~4의 스크린샷 placeholder를 보관한다.

| 파일명 | 캡처 대상 | 캡처 시점 |
|---|---|---|
| `onboarding-step-1-login.png` | `/login` 화면 + 비밀번호 변경 강제 안내 모달 | Story 5.1 완료 후 |
| `onboarding-step-2-upload.png` | `/admin/rag/data` TXT 업로드 + dry-run 검증 결과 | Story 8.1 완료 후 |
| `onboarding-step-3-rebuild.png` | `/admin/rag/data` SSE 진행률 배너 (재빌드 중) | Story 8.3 완료 후 |
| `onboarding-step-4-broadcast.png` | `/admin/content` RichTextEditor + 세그먼트 필터 | Story 7.1 완료 + HOLD-MSG 해제 후 |

## 캡처 가이드

- 해상도: 1920x1080 권장 (Retina 디스플레이는 2배 크기)
- 포맷: PNG (투명 배경 불필요)
- 마스킹: 실 사용자 PII(이메일·휴대폰·이름) 가림 처리 필수
- 색역: sRGB

`docs/ONBOARDING.md`의 `![screenshot](./screenshots/onboarding-step-N.png)` 링크는 본 디렉터리에 동일 파일명으로 저장하면 자동 렌더링된다.

현 시점에는 placeholder가 깨져 보일 수 있으나 본 README의 존재로 마크다운 렌더링 시 디렉터리는 인지된다. 실제 PNG 파일은 인수 데모 시점에 캡처해 추가.

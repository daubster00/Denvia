/**
 * 로그인 세션과 QA 대화를 **함께** 초기화하는 단일 지점 — 재수정 P0-2.
 *
 * ## 왜 공통 함수가 필요한가
 *
 * 세션이 끝나는 길은 여러 갈래다.
 *
 *   0. 사용자가 회원 탈퇴를 완료한다
 *   1. 사용자가 로그아웃 버튼을 누른다
 *   2. 보호 API 가 401 을 돌려준다 (세션 만료)
 *   3. SSE 스트림이 401 로 거절된다
 *   4. 다른 곳에서 같은 계정으로 로그인돼 이 세션이 무효화된다 (중복 로그인)
 *   5. `?login=superseded` 로 돌아온 화면에서 안내를 띄운다
 *   6. 앱 부팅 시 `/api/v1/me` 가 실패한다
 *
 * 예전에는 각 경로가 **제각기** 정리했다. 어떤 길은 `clearSession()`(로그인 사용자
 * 비우기)만 하고 `denvia-qa-store`(QA 대화가 담긴 sessionStorage 키)는 그대로 뒀다.
 * 그러면 같은 탭에서 다음 사용자가 들어왔을 때 **이전 사용자의 대화**가 남아 다음
 * 질문의 맥락(`history_turn_ids`)으로 전송된다.
 *
 * 정리 지점을 한 곳으로 모아 "한 길만 빠뜨리는" 실수를 구조적으로 막는다.
 *
 * ## 유지해야 하는 것
 *
 * **같은 사용자의 새로고침·페이지 이동에서는 대화를 지우지 않는다.** 그 판정은
 * `useQAStore.setOwner(userId)`(대화 주인 확정)가 담당한다 — 주인이 바뀔 때만 비운다.
 * 이 함수는 "세션이 끝났다" 가 확실한 경우에만 호출한다.
 */

import { useQAStore } from "@/stores/qa-store";
import { useSessionStore } from "@/stores/session-store";
import { ApiError } from "@/types/api";

/** 세션 종료 사유 — 로그·진단용. 동작은 모두 같다(전부 비운다). */
export type SessionEndReason =
  | "logout"
  | "api_401"
  | "sse_401"
  | "session_expired"
  | "superseded"
  | "bootstrap_failed";

/**
 * 로그인 세션 + QA 대화를 함께 비운다.
 *
 * zustand 스토어를 훅 밖에서(React 컴포넌트가 아닌 곳에서) 쓰기 때문에
 * `getState()` 로 접근한다 — `api-client.ts` 같은 모듈에서도 호출된다.
 */
export function resetClientSession(_reason: SessionEndReason): void {
  useSessionStore.getState().clearSession();
  useQAStore.getState().resetForSessionEnd();
}

/**
 * 이 오류가 **"서버가 더 이상 우리를 모른다"** 를 뜻하는가 (3차 검수 P1-1).
 *
 * 세션 복원(`GET /api/v1/me`)이 실패하는 이유는 인증 만료만이 아니다. 500·502·
 * 네트워크 단절도 같은 "실패" 로 들어온다. 그 전부를 세션 종료로 취급하면,
 * **배포 중 20초간의 502 나 모바일 터널링만으로 진행 중인 대화가 통째로 사라진다**
 * (sessionStorage 를 지워 버리므로 서버가 복구돼도 돌아오지 않는다).
 *
 * 그래서 인증 실패로 확인된 경우에만 대화를 비운다. 백엔드 인증 오류 코드는 모두
 * `AUTH_` 접두사(만료·무효토큰·중복로그인·미인증) 또는 `ACCOUNT_BLOCKED` 다.
 */
export function isAuthFailure(error: unknown): boolean {
  if (!(error instanceof ApiError)) return false;
  const code = error.code ?? "";
  return code.startsWith("AUTH_") || code === "ACCOUNT_BLOCKED";
}

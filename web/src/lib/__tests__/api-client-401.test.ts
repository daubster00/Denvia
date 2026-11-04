/**
 * 공용 API 클라이언트의 401 처리 — 2026-11-03 재수정 P0-2.
 *
 * 보호 API 가 401 을 돌려주면 로그인 세션과 **QA 대화**를 함께 비워야 한다.
 * 예전에는 `clearSession()`(로그인 사용자 비우기)만 호출해 `denvia-qa-store`
 * (QA 대화 sessionStorage 키)가 남았고, 같은 탭의 다음 사용자가 이전 사용자의
 * 대화를 그대로 질문 맥락으로 보냈다.
 *
 * jsdom 에서 `window.location.replace` 는 동작하지 않으므로, 리다이렉트가 일어나지
 * 않는 경로(홈 `/` 에서의 401)와 중복 로그인(superseded)을 각각 검증한다.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "@/lib/api-client";
import { useQAStore, type QAMessage } from "@/stores/qa-store";
import { useSessionStore } from "@/stores/session-store";

const TURN: QAMessage[] = [
  {
    id: "u1",
    role: "user",
    content: "스케일링 산정 기준",
    status: "complete",
    timestamp: "2026-01-01T00:00:00.000Z",
  },
  {
    id: "a1",
    role: "assistant",
    content: "3분의1악당 1회입니다.",
    status: "complete",
    qaLogId: 101,
    timestamp: "2026-01-01T00:00:00.000Z",
  },
];

function mockResponse(status: number, body: Record<string, unknown>): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: "",
    headers: { get: () => null },
    json: async () => body,
  } as unknown as Response;
}

function seedConversation() {
  useQAStore.setState({
    messages: [...TURN],
    pendingHomeQuestion: "대기 질문",
    ownerUserId: 7,
  });
  useSessionStore.setState({ user: { user_id: 7 } } as never);
}

function expectEverythingCleared() {
  const qa = useQAStore.getState();
  expect(qa.messages).toEqual([]);
  expect(qa.pendingHomeQuestion).toBeNull();
  expect(qa.ownerUserId).toBeNull();
  expect(useSessionStore.getState().user).toBeNull();
}

beforeEach(() => {
  vi.restoreAllMocks();
  useQAStore.setState({ messages: [], pendingHomeQuestion: null, ownerUserId: null });
  useSessionStore.setState({ user: null, isPopupOpen: false } as never);
  // 홈에 있는 상태로 둔다 — api-client 가 페이지 이동 없이 로그인 팝업만 띄운다.
  window.history.replaceState({}, "", "/");
});

// jsdom 의 location.replace 는 구현돼 있지 않아 실행 시 "Not implemented" 를 던진다.
// 재정의도 막혀 있어(configurable: false) spyOn 이 안 되므로, location 자체를
// 치환 가능한 객체로 한 번 바꿔 둔다. 테스트가 보는 것은 "대화가 비워졌는가" 이고
// 이동 자체는 이 파일의 관심사가 아니다.
Object.defineProperty(window, "location", {
  configurable: true,
  writable: true,
  value: {
    ...window.location,
    href: "http://localhost/",
    pathname: "/",
    replace: () => {},
  },
});

describe("세션 만료 401 (재수정 P0-2)", () => {
  it("QA 대화와 로그인 세션을 모두 비운다", async () => {
    seedConversation();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      mockResponse(401, {
        code: "AUTH_SESSION_EXPIRED",
        message: "세션이 만료되었습니다.",
      }),
    );

    await expect(apiFetch("/api/v1/me/quota")).rejects.toThrow();

    expectEverythingCleared();
  });

  it("비운 뒤 다른 계정이 들어와도 이전 대화가 돌아오지 않는다", async () => {
    seedConversation();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      mockResponse(401, { code: "AUTH_SESSION_EXPIRED", message: "만료" }),
    );

    await expect(apiFetch("/api/v1/me/quota")).rejects.toThrow();
    useQAStore.getState().setOwner(8);

    expect(useQAStore.getState().messages).toEqual([]);
  });
});

describe("중복 로그인 401 — AUTH_SESSION_SUPERSEDED (재수정 P0-2)", () => {
  it("QA 대화와 로그인 세션을 모두 비운다", async () => {
    seedConversation();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      mockResponse(401, {
        code: "AUTH_SESSION_SUPERSEDED",
        message: "다른 장소에서 로그인되었습니다.",
      }),
    );

    await expect(apiFetch("/api/v1/me")).rejects.toThrow();

    expectEverythingCleared();
  });
});

describe("401 이 아닌 응답에서는 대화를 건드리지 않는다", () => {
  it("성공 응답은 대화를 유지한다 (같은 사용자 사용 중)", async () => {
    seedConversation();
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      status: 200,
      headers: { get: () => null },
      json: async () => ({ ok: true }),
    } as unknown as Response);

    await apiFetch("/api/v1/me/quota");

    expect(useQAStore.getState().messages.map((m) => m.id)).toEqual(["u1", "a1"]);
    expect(useQAStore.getState().ownerUserId).toBe(7);
  });

  it("500 오류도 대화를 지우지 않는다 (세션이 끝난 것이 아니다)", async () => {
    seedConversation();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      mockResponse(500, { code: "INTERNAL_ERROR", message: "서버 오류" }),
    );

    await expect(apiFetch("/api/v1/me/quota")).rejects.toThrow();

    expect(useQAStore.getState().messages.map((m) => m.id)).toEqual(["u1", "a1"]);
  });
});

/**
 * 관리자 "대화 이어가기" 설정 폼의 재조회 반영 — 2026-11-03 재수정 P1-3.
 *
 * ## 무엇이 틀렸었나
 *
 * 재초기화 여부를 `dirty`(= 화면 값이 서버 값과 다른가)로 판정했다. 그 판정은
 * **다른 관리자가 값을 바꾼 순간** 참이 된다 — 내가 아무것도 건드리지 않았는데도
 * 내 화면 값이 새 서버 값과 달라지기 때문이다. 그러면 재조회가 영구히 반영되지 않고,
 * 그 상태로 저장하면 상대의 변경을 옛 값으로 덮어쓴다.
 *
 * ## 고정하는 것
 *   1. 편집하지 않은 폼은 재조회된 서버 값으로 초기화된다.
 *   2. 편집 중인 폼은 사용자 입력을 보존한다.
 *   3. 저장 성공 후에는 편집 상태가 풀려, 다음 재조회가 다시 반영된다.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/admin/settings",
  useSearchParams: () => new URLSearchParams(),
}));

const fetchChatHistoryConfigMock = vi.fn();
const updateChatHistoryConfigMock = vi.fn();
vi.mock("@/features/admin-dashboard/api/chatHistory", () => ({
  fetchChatHistoryConfig: () => fetchChatHistoryConfigMock(),
  updateChatHistoryConfig: (p: unknown) => updateChatHistoryConfigMock(p),
}));

// 같은 페이지의 다른 카드들은 이 테스트의 관심사가 아니다 — 로딩 실패로 둬도
// 대화 이어가기 카드는 독립적으로 렌더된다.
vi.mock("@/features/admin-dashboard/api/budget", () => ({
  fetchBudgetCurrentMonth: () => Promise.reject(new Error("skip")),
  updateMonthlyBudgetLimit: () => Promise.reject(new Error("skip")),
}));
vi.mock("@/features/admin-dashboard/api/chatModel", () => ({
  fetchChatModelConfig: () => Promise.reject(new Error("skip")),
  updateChatModelConfig: () => Promise.reject(new Error("skip")),
  formatModelPrice: () => "",
}));
vi.mock("@/features/admin-dashboard/api/forex", () => ({
  fetchForexConfig: () => Promise.reject(new Error("skip")),
}));

import SettingsPage from "@/app/admin/settings/page";
import type { ChatHistoryConfig } from "@/features/admin-dashboard/api/chatHistory";

const HISTORY_QUERY_KEY = ["admin", "runtime-config", "chat-history"];

function makeConfig(over: Partial<ChatHistoryConfig> = {}): ChatHistoryConfig {
  return {
    enabled: true,
    max_turns: 5,
    max_tokens: 3000,
    rewriter_model: "gpt-6-luna",
    models: [
      {
        model_id: "gpt-6-luna",
        label: "GPT-6 Luna",
        output_usd_per_mtok: 0.4,
      },
      {
        model_id: "gpt-6-terra",
        label: "GPT-6 Terra",
        output_usd_per_mtok: 1.2,
      },
    ] as ChatHistoryConfig["models"],
    default_max_turns: 5,
    default_max_tokens: 3000,
    ...over,
  };
}

function renderPage(initial: ChatHistoryConfig) {
  fetchChatHistoryConfigMock.mockResolvedValue(initial);
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const view = render(
    <QueryClientProvider client={client}>
      <SettingsPage />
    </QueryClientProvider>,
  );
  return { client, view };
}

/** 다른 관리자가 값을 바꿔 재조회된 상황을 만든다. */
function serverChangesTo(client: QueryClient, next: ChatHistoryConfig) {
  client.setQueryData(HISTORY_QUERY_KEY, next);
}

const turnsInput = () =>
  screen.getByLabelText(/참고할 최근 대화 수/) as HTMLInputElement;
const tokensInput = () =>
  screen.getByLabelText(/이전 대화 분량 상한/) as HTMLInputElement;
const modelSelect = () =>
  screen.getByLabelText(/연관성 판단에 쓸 모델/) as HTMLSelectElement;
const enabledCheckbox = () =>
  screen.getByLabelText(/앞선 대화를 참고해서 답변하기/) as HTMLInputElement;
const saveButton = () => screen.getByRole("button", { name: /저장/ });

beforeEach(() => {
  vi.clearAllMocks();
});

describe("편집하지 않은 폼 (재수정 P1-3)", () => {
  it("재조회된 서버 값으로 초기화된다", async () => {
    const { client } = renderPage(makeConfig());
    await waitFor(() => expect(turnsInput().value).toBe("5"));

    serverChangesTo(
      client,
      makeConfig({ max_turns: 12, max_tokens: 8000, rewriter_model: "gpt-6-terra" }),
    );

    await waitFor(() => expect(turnsInput().value).toBe("12"));
    expect(tokensInput().value).toBe("8000");
    expect(modelSelect().value).toBe("gpt-6-terra");
  });

  it("체크박스(사용 여부)도 새 값으로 따라온다", async () => {
    const { client } = renderPage(makeConfig({ enabled: true }));
    await waitFor(() => expect(enabledCheckbox().checked).toBe(true));

    serverChangesTo(client, makeConfig({ enabled: false }));

    await waitFor(() => expect(enabledCheckbox().checked).toBe(false));
  });
});

describe("편집 중인 폼 (재수정 P1-3)", () => {
  it("재조회가 와도 사용자 입력을 보존한다", async () => {
    const user = userEvent.setup();
    const { client } = renderPage(makeConfig());
    await waitFor(() => expect(turnsInput().value).toBe("5"));

    // 사용자가 입력을 바꾼다.
    await user.clear(turnsInput());
    await user.type(turnsInput(), "9");
    expect(turnsInput().value).toBe("9");

    // 그 사이 다른 관리자가 값을 바꿨다.
    serverChangesTo(client, makeConfig({ max_turns: 12, max_tokens: 8000 }));

    // 입력하던 값은 그대로다.
    await waitFor(() => expect(turnsInput().value).toBe("9"));
    // 건드리지 않은 다른 필드도 편집 중에는 함께 보존한다(폼 단위 판정).
    expect(tokensInput().value).toBe("3000");
  });

  it("값을 원래대로 되돌려도 편집 중 상태는 유지된다", async () => {
    const user = userEvent.setup();
    const { client } = renderPage(makeConfig());
    await waitFor(() => expect(turnsInput().value).toBe("5"));

    await user.clear(turnsInput());
    await user.type(turnsInput(), "9");
    await user.clear(turnsInput());
    await user.type(turnsInput(), "5");   // 서버 값과 같아졌다

    serverChangesTo(client, makeConfig({ max_turns: 12 }));

    // `dirty`(서버 값과의 차이)로 판정하면 여기서 12 로 덮어써진다.
    await waitFor(() => expect(turnsInput().value).toBe("5"));
  });
});

describe("저장 성공 후 (재수정 P1-3)", () => {
  it("편집 상태가 풀려 다음 재조회가 다시 반영된다", async () => {
    const user = userEvent.setup();
    const saved = makeConfig({ max_turns: 9 });
    updateChatHistoryConfigMock.mockResolvedValue(saved);

    const { client } = renderPage(makeConfig());
    await waitFor(() => expect(turnsInput().value).toBe("5"));

    await user.clear(turnsInput());
    await user.type(turnsInput(), "9");
    await user.click(saveButton());

    // 이 저장소 vitest 설정에는 jest-dom 매처가 없다 — 존재 여부만 직접 본다.
    await waitFor(() =>
      expect(screen.getByText(/저장되었습니다/)).toBeTruthy(),
    );
    expect(updateChatHistoryConfigMock).toHaveBeenCalledWith({
      enabled: true,
      max_turns: 9,
      max_tokens: 3000,
      rewriter_model: "gpt-6-luna",
    });

    // 저장 뒤 다른 관리자가 또 바꾼다 → 이번에는 반영돼야 한다.
    serverChangesTo(client, makeConfig({ max_turns: 15, max_tokens: 9000 }));

    await waitFor(() => expect(turnsInput().value).toBe("15"));
    expect(tokensInput().value).toBe("9000");
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 끈 상태에서 막히지 않는다 — 3차 검수 P2
//
// 입력란을 비운 뒤 "사용 안 함" 으로 끄면, 저장 버튼은 값이 유효하지 않아 비활성이고
// 입력란은 꺼져 있어 비활성 → **저장도 수정도 못 하는 막힌 상태**가 됐다.
// ─────────────────────────────────────────────────────────────────────────────

describe("사용 안 함으로 끈 상태 (3차 검수 P2)", () => {
  it("입력란을 비운 뒤 끄더라도 저장할 수 있다", async () => {
    const user = userEvent.setup();
    updateChatHistoryConfigMock.mockResolvedValue(makeConfig({ enabled: false }));
    renderPage(makeConfig());
    await waitFor(() => expect(turnsInput().value).toBe("5"));

    await user.clear(turnsInput());          // 값이 비어 유효하지 않은 상태
    await user.click(enabledCheckbox());     // 끄면 입력란이 비활성된다

    expect(enabledCheckbox().checked).toBe(false);
    expect(turnsInput().disabled).toBe(true);
    // 막히지 않는다 — 저장 버튼이 살아 있어야 한다.
    expect((saveButton() as HTMLButtonElement).disabled).toBe(false);

    await user.click(saveButton());

    await waitFor(() => expect(updateChatHistoryConfigMock).toHaveBeenCalled());
    // 비어 있던 값 대신 **서버 현재값**을 보낸다 (0 이 저장되면 다시 켤 때 범위 밖이 된다).
    expect(updateChatHistoryConfigMock).toHaveBeenCalledWith({
      enabled: false,
      max_turns: 5,
      max_tokens: 3000,
      rewriter_model: "gpt-6-luna",
    });
  });

  it("끈 상태에서는 숫자 범위 오류 문구를 띄우지 않는다", async () => {
    const user = userEvent.setup();
    renderPage(makeConfig());
    await waitFor(() => expect(turnsInput().value).toBe("5"));

    await user.clear(turnsInput());
    await user.click(enabledCheckbox());

    expect(screen.queryByText(/1~20 사이의 정수/)).toBeNull();
  });

  it("켜진 상태에서는 범위 검증이 그대로 동작한다 (회귀 금지)", async () => {
    const user = userEvent.setup();
    renderPage(makeConfig());
    await waitFor(() => expect(turnsInput().value).toBe("5"));

    await user.clear(turnsInput());
    await user.type(turnsInput(), "99");   // 상한 20 초과

    expect((saveButton() as HTMLButtonElement).disabled).toBe(true);
    await waitFor(() =>
      expect(screen.getByText(/1~20 사이의 정수/)).toBeTruthy(),
    );
  });
});

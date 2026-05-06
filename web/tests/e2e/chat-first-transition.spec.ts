import { test, expect } from "@playwright/test";

/**
 * Story 2.7 — Chat-First 전환 E2E (AC-1, AC-3, AC-4).
 *
 * /(메인) ↔ /chat 분리 라우팅:
 * - / 비로그인: 히어로 카피 + readonly ChatInput
 * - / 로그인: 히어로 카피 + 활성 ChatInput — 제출 시 /chat 으로 이동
 * - / 는 messages 존재 여부와 무관하게 항상 hero 만 렌더 (ChatShell 미렌더).
 * - /chat: messages=0 → 활성 hero ChatInput / messages>=1 → ChatShell.
 *
 * 라이브 백엔드 의존성을 제거하기 위해 /api/v1/me, /api/v1/qa/stream을 page.route로 mock.
 */

const MOCK_USER = {
  user_id: 42,
  email: "doc@denvia.com",
  role: "user",
  subscription_status: "pro",
  segment: "doctor",
  years_of_experience: 10,
  must_reset_password: false,
  is_social: false,
};

test.describe("Story 2.7 — Chat-First 자동 전환", () => {
  test.beforeEach(async ({ page }) => {
    await page.route("**/api/v1/me", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(MOCK_USER),
      })
    );
  });

  test("AC-1: / 진입 시 messages=0 → 히어로 카피 + 활성 textarea, 메시지 영역 미렌더", async ({ page }) => {
    await page.goto("/");
    // 활성 textarea(=interactive hero)가 렌더되어야 한다.
    const input = page.getByRole("textbox", { name: "질문 입력" });
    await expect(input).toBeVisible();
    // 히어로 카피가 보여야 한다.
    await expect(page.getByText("AI가 참고 답변을 드립니다")).toBeVisible();
    // hero 상태에서는 메시지 영역(role=log)이 마운트되지 않는다.
    await expect(page.getByRole("log", { name: "대화 내역" })).toHaveCount(0);
  });

  test("AC-1: /chat 에서 messages>=1 시 ChatShell inline 노출 (히어로 카피 숨김 + 메시지 영역 노출)", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("textbox", { name: "질문 입력" })).toBeVisible();

    // qa-store 직접 주입: 첫 질문이 들어온 상황을 시뮬레이션 (SSE mock 복잡도 회피).
    await page.evaluate(() => {
      const stored = sessionStorage.getItem("denvia-qa-store");
      const parsed = stored
        ? JSON.parse(stored)
        : { state: { messages: [] }, version: 0 };
      parsed.state.messages = [
        {
          id: "u1",
          role: "user",
          content: "임플란트 보험 적용 기준?",
          status: "complete",
          timestamp: "2026-04-27T00:00:00.000Z",
        },
        {
          id: "a1",
          role: "assistant",
          content: "임플란트 보험은 만 65세 이상 평생 2개까지 적용됩니다.",
          status: "complete",
          timestamp: "2026-04-27T00:00:01.000Z",
        },
      ];
      sessionStorage.setItem("denvia-qa-store", JSON.stringify(parsed));
    });

    // /(메인)은 메시지가 있어도 항상 hero — ChatShell 은 /chat 에서만 렌더된다.
    await page.goto("/chat");

    // inline 상태: 메시지 영역 + 메시지 본문 + 하단 입력창 모두 보여야 한다.
    await expect(page.getByRole("log", { name: "대화 내역" })).toBeVisible();
    await expect(page.getByText("임플란트 보험 적용 기준?")).toBeVisible();
    await expect(page.getByRole("textbox", { name: "질문 입력" })).toBeVisible();
    // 히어로 카피는 사라져야 한다.
    await expect(page.getByText("AI가 참고 답변을 드립니다")).toHaveCount(0);
  });

  test("AC-3: 환경변수 설정 시 우측 하단 고객문의 FAB 렌더 + aria-label 확인", async ({ page }) => {
    await page.goto("/");
    const fab = page.getByRole("button", {
      name: "고객문의 — 카카오톡 채널 열기",
    });
    await expect(fab).toBeVisible();
  });

  test("/chat 직접 진입 시 messages=0 → 활성 hero ChatInput 노출", async ({ page }) => {
    await page.goto("/chat");
    await expect(page).toHaveURL(/\/chat$/);
    await expect(page.getByRole("textbox", { name: "질문 입력" })).toBeVisible();
  });

  test("AC-3: FAB 클릭 시 새 탭이 열리고 noopener,noreferrer가 적용된다", async ({ page, context }) => {
    await page.goto("/");
    const fab = page.getByRole("button", {
      name: "고객문의 — 카카오톡 채널 열기",
    });

    const [popup] = await Promise.all([
      context.waitForEvent("page"),
      fab.click(),
    ]);
    // window.open(..., "_blank", "noopener,noreferrer") → opener는 null이어야 한다.
    const opener = await popup.evaluate(() => window.opener);
    expect(opener).toBeNull();
    await popup.close();
  });
});

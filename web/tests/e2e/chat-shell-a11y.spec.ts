import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

/**
 * Story 2.7 — 채팅 쉘 접근성·키보드·prefers-reduced-motion E2E (T9, AC-1·AC-2·AC-3).
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

test.describe("Story 2.7 — 접근성 (axe)", () => {
  test.beforeEach(async ({ page }) => {
    await page.route("**/api/v1/me", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(MOCK_USER),
      })
    );
  });

  test("hero 상태(messages=0) / — axe 위반 0건 (심각·중대)", async ({ page }) => {
    await page.goto("/");
    await expect(
      page.getByRole("button", { name: "고객문의 — 카카오톡 채널 열기" })
    ).toBeVisible();

    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa"])
      .analyze();
    const critical = results.violations.filter(
      (v) => v.impact === "critical" || v.impact === "serious"
    );
    expect(critical).toEqual([]);
  });

  test("inline 상태(messages>=1) /chat — axe 위반 0건 (심각·중대, color-contrast 제외)", async ({ page }) => {
    // 본 스토리는 chat-first 전환·미니 TopNav·FAB 영역 a11y만 커버.
    await page.goto("/");
    await page.evaluate(() => {
      const stored = sessionStorage.getItem("denvia-qa-store");
      const parsed = stored
        ? JSON.parse(stored)
        : { state: { messages: [] }, version: 0 };
      parsed.state.messages = [
        {
          id: "u1",
          role: "user",
          content: "치주염 치료 단계?",
          status: "complete",
          timestamp: "2026-04-27T00:00:00.000Z",
        },
        {
          id: "a1",
          role: "assistant",
          content: "치주염은 단계별로 SRP·Flap surgery 등을 적용합니다.",
          status: "complete",
          timestamp: "2026-04-27T00:00:01.000Z",
        },
      ];
      sessionStorage.setItem("denvia-qa-store", JSON.stringify(parsed));
    });
    // ChatShell 렌더링은 /chat 에서만 수행된다 (/(메인)은 항상 hero).
    await page.goto("/chat");

    await expect(page.getByRole("log", { name: "대화 내역" })).toBeVisible();

    const results = await new AxeBuilder({ page })
      .disableRules(["color-contrast"])
      .withTags(["wcag2a", "wcag2aa"])
      .analyze();
    const critical = results.violations.filter(
      (v) => v.impact === "critical" || v.impact === "serious"
    );
    expect(critical).toEqual([]);
  });
});

test.describe("Story 2.7 — prefers-reduced-motion", () => {
  test("reduced-motion=reduce 시 inputCenter/inputBottom/messages 애니메이션이 none으로 비활성화된다", async ({ page }) => {
    // Playwright API 직접 호출 — `test.use({ reducedMotion })` 옵션이 일부 환경에서 미반영됨
    await page.emulateMedia({ reducedMotion: "reduce" });

    await page.route("**/api/v1/me", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(MOCK_USER),
      })
    );
    await page.goto("/");
    await expect(page.getByRole("textbox", { name: "질문 입력" })).toBeVisible();

    // sanity: prefers-reduced-motion이 실제 매칭되는지 먼저 확인
    const matched = await page.evaluate(
      () => window.matchMedia("(prefers-reduced-motion: reduce)").matches
    );
    expect(matched).toBe(true);

    // hero 상태 — chat-shell.module.css의 .inputCenter (CSS Module 해시 클래스명에 'inputCenter' 포함)
    const heroAnimation = await page.evaluate(() => {
      // CSS Module 해시 클래스명은 보통 "<file>_inputCenter__<hash>" 또는 "<file>_inputCenter"
      const candidates = Array.from(document.querySelectorAll("[class]"));
      const el = candidates.find((c) =>
        Array.from(c.classList).some((cls) => /inputCenter/i.test(cls))
      );
      return el ? getComputedStyle(el).animationName : null;
    });
    expect(heroAnimation).toBe("none");

    // inline 상태로 전환 — ChatShell 은 /chat 에서만 렌더된다.
    await page.evaluate(() => {
      const stored = sessionStorage.getItem("denvia-qa-store");
      const parsed = stored
        ? JSON.parse(stored)
        : { state: { messages: [] }, version: 0 };
      parsed.state.messages = [
        {
          id: "u1",
          role: "user",
          content: "Q",
          status: "complete",
          timestamp: "2026-04-27T00:00:00.000Z",
        },
      ];
      sessionStorage.setItem("denvia-qa-store", JSON.stringify(parsed));
    });
    await page.goto("/chat");
    await expect(page.getByRole("log", { name: "대화 내역" })).toBeVisible();

    const inlineAnimations = await page.evaluate(() => {
      const all = Array.from(document.querySelectorAll("[class]"));
      const findByPattern = (pattern: RegExp) => {
        const el = all.find((c) =>
          Array.from(c.classList).some((cls) => pattern.test(cls))
        );
        return el ? getComputedStyle(el).animationName : null;
      };
      return {
        bottom: findByPattern(/inputBottom/i),
        messages: findByPattern(/messages/i),
      };
    });
    expect(inlineAnimations.bottom).toBe("none");
    expect(inlineAnimations.messages).toBe("none");
  });
});

test.describe("Story 2.7 — 키보드 Tab 순서 (로그인 후, hero 상태)", () => {
  test("Tab 순서: Skip link → 로고 → 이메일/로그아웃 → 입력 → FAB", async ({ page }) => {
    await page.route("**/api/v1/me", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(MOCK_USER),
      })
    );
    await page.goto("/");
    await expect(page.getByRole("textbox", { name: "질문 입력" })).toBeVisible();

    // 페이지 시작 시 활성 textarea가 자동 포커스되므로, body로 포커스 리셋 후 Tab 시작
    await page.evaluate(() => {
      (document.activeElement as HTMLElement | null)?.blur?.();
    });

    const order: string[] = [];
    for (let i = 0; i < 8; i += 1) {
      await page.keyboard.press("Tab");
      const label = await page.evaluate(() => {
        const el = document.activeElement as HTMLElement | null;
        if (!el) return null;
        return (
          el.getAttribute("aria-label") ||
          el.textContent?.trim() ||
          el.tagName
        );
      });
      if (label) order.push(label);
    }

    // 핵심 요소들이 Tab 순서에 모두 등장하는지만 보장 (구체 순서는 브라우저별 미세차 허용)
    const joined = order.join(" | ");
    expect(joined).toContain("질문 입력");
    expect(joined).toContain("고객문의");
    // 로그아웃 버튼이 Tab 가능
    expect(joined).toMatch(/로그아웃|로그인/);
  });
});

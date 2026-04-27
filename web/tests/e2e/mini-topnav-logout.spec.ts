import { test, expect } from "@playwright/test";

/**
 * Story 2.7 — 미니 TopNav · 로그아웃 흐름 E2E (AC-2).
 *
 * 백엔드 의존성 제거를 위해 /api/v1/me, /api/v1/auth/logout을 page.route로 mock.
 */

const MOCK_USER = {
  user_id: 42,
  email: "doc@denvia.com",
  role: "user",
  subscription_status: "pro",
  segment: "doctor",
  years_of_experience: 10,
  must_reset_password: false,
};

test.describe("Story 2.7 — 미니 TopNav user 분기", () => {
  test("로그인 후: 이메일 + 로그아웃 버튼 노출 / '로그인' 버튼 비노출", async ({ page }) => {
    await page.route("**/api/v1/me", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(MOCK_USER),
      })
    );

    await page.goto("/");

    await expect(page.getByText("doc@denvia.com")).toBeVisible();
    await expect(page.getByRole("button", { name: "로그아웃" })).toBeVisible();
    await expect(page.getByRole("button", { name: "로그인" })).toHaveCount(0);
  });

  test("로그아웃 클릭 → POST /auth/logout 호출 + '/' 리다이렉트 + 비로그인 TopNav 복귀", async ({ page }) => {
    let logoutCalled = false;

    let meHits = 0;
    await page.route("**/api/v1/me", (route) => {
      meHits += 1;
      if (logoutCalled) {
        // 로그아웃 후 SessionBootstrap 재요청은 401을 반환하여 비로그인으로 전환.
        return route.fulfill({
          status: 401,
          contentType: "application/json",
          body: JSON.stringify({
            code: "AUTH_NOT_AUTHENTICATED",
            message: "로그인이 필요합니다.",
            trace_id: `t-${meHits}`,
          }),
        });
      }
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(MOCK_USER),
      });
    });

    await page.route("**/api/v1/auth/logout", (route) => {
      logoutCalled = true;
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        headers: { "set-cookie": "denvia_session=; Max-Age=0; Path=/" },
        body: "",
      });
    });

    await page.goto("/");
    await expect(page.getByRole("button", { name: "로그아웃" })).toBeVisible();

    await page.getByRole("button", { name: "로그아웃" }).click();

    // '/'로 리다이렉트되어 비로그인 TopNav가 복귀해야 한다.
    await page.waitForURL("**/");
    await expect(page.getByRole("button", { name: "로그인" })).toBeVisible();
    expect(logoutCalled).toBe(true);
  });
});

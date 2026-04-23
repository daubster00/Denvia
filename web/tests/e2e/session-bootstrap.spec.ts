import { test, expect } from "@playwright/test";

test.describe("세션 Bootstrap — 비로그인 랜딩 정상 경로", () => {
  test("비로그인 랜딩 접속 시 /me 401 수신 후 팝업 자동 오픈 안 됨", async ({ page }) => {
    // /api/v1/me → 401 mock
    await page.route("**/api/v1/me", (route) => {
      route.fulfill({
        status: 401,
        contentType: "application/json",
        body: JSON.stringify({
          code: "AUTH_NOT_AUTHENTICATED",
          message: "로그인이 필요합니다.",
          trace_id: "test-trace",
        }),
      });
    });

    await page.goto("/");

    // 잠시 대기 (세션 쿼리 완료)
    await page.waitForTimeout(1000);

    // 팝업이 자동으로 열리지 않아야 함 (비로그인 랜딩 정상 경로)
    await expect(page.getByRole("dialog")).not.toBeVisible();

    // 랜딩 페이지는 정상 렌더
    await expect(page.getByText("Denvia")).toBeVisible();
  });
});

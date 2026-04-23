import { test, expect } from "@playwright/test";

test.describe("F-000 메인 랜딩 페이지", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
  });

  test("/ 루트 접속 시 200 응답 + 로고 렌더", async ({ page }) => {
    await expect(page.getByText("Denvia")).toBeVisible();
  });

  test("서비스 소개 카피가 표시된다", async ({ page }) => {
    await expect(page.getByText("치과 임상 질문")).toBeVisible();
  });

  test("Advisory 면책 고지가 표시된다 (NFR-C6)", async ({ page }) => {
    await expect(page.getByText("본 답변은 참고용이며 의학적 판단은 전문가 책임")).toBeVisible();
  });

  test("우상단 로그인 버튼이 있다", async ({ page }) => {
    await expect(page.getByRole("button", { name: "로그인" })).toBeVisible();
  });

  test("로그인 버튼 클릭 → 로그인 팝업 open", async ({ page }) => {
    await page.getByRole("button", { name: "로그인" }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await expect(page.getByRole("tab", { name: "이메일" })).toBeVisible();
  });

  test("ChatInput 클릭 → 로그인 팝업 open", async ({ page }) => {
    const chatInput = page.getByRole("textbox");
    await chatInput.click();
    await expect(page.getByRole("dialog")).toBeVisible();
  });
});

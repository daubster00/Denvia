import { test, expect } from "@playwright/test";

test.describe("F-000 메인 랜딩 페이지", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
  });

  test("/ 루트 접속 시 200 응답 + 로고 렌더", async ({ page }) => {
    // "Denvia"는 메타·로고·푸터 등 다수 노출되므로 로고 링크로 unique 매칭.
    await expect(page.getByRole("link", { name: /Denvia 홈/ })).toBeVisible();
  });

  test("서비스 소개 카피가 표시된다", async ({ page }) => {
    await expect(page.getByText("Denvia AI에게 질문하세요.")).toBeVisible();
  });

  test("우상단 로그인 버튼이 있다", async ({ page }) => {
    await expect(page.getByRole("button", { name: "로그인" })).toBeVisible();
  });

  test("로그인 버튼 클릭 → 로그인 팝업 open", async ({ page }) => {
    await page.getByRole("button", { name: "로그인" }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    // 로그인 다이얼로그 안에 '이메일' 입력 폼이 노출된다 (구버전 tab role 제거됨).
    await expect(page.getByRole("dialog").getByText(/이메일/).first()).toBeVisible();
  });

  test("ChatInput 클릭 → 로그인 팝업 open", async ({ page }) => {
    const chatInput = page.getByRole("textbox");
    await chatInput.click();
    await expect(page.getByRole("dialog")).toBeVisible();
  });
});

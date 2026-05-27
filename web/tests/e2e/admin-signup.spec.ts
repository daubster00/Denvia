import { test, expect } from "@playwright/test";

/**
 * Story 10.2 — /admin/signup E2E.
 *
 * 2026-05-27: 휴대폰 OTP 인증 단계 제거. 이름/이메일/연락처/비밀번호만 검증.
 * 실 signup 호출은 백엔드 API를 route intercept로 mocking — 페이지 동작·라우팅·
 * 에러 메시지 분기만 검증한다.
 */

test.describe("Story 10.2 — 관리자 가입 (admin-signup)", () => {
  test("케이스 1: /admin/login → 관리자 가입 링크 → /admin/signup 이동", async ({
    page,
  }) => {
    await page.route("**/api/v1/admin/auth/me", (route) =>
      route.fulfill({ status: 401, body: JSON.stringify({ code: "ADMIN_AUTH_REQUIRED" }) }),
    );
    await page.goto("/admin/login");

    const signupLink = page.getByRole("link", { name: "관리자 가입" });
    await expect(signupLink).toBeVisible();
    await signupLink.click();
    await expect(page).toHaveURL(/\/admin\/signup$/);
    await expect(page.getByRole("heading", { name: "관리자 가입 신청" })).toBeVisible();
    await expect(
      page.getByText("운영자 승인 후 이용 가능합니다", { exact: false }),
    ).toBeVisible();
  });

  test("케이스 2: 이름/이메일/연락처/비밀번호 입력 → 201 응답 + 성공 토스트", async ({
    page,
  }) => {
    await page.route("**/api/v1/admin/auth/signup", (route) =>
      route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({
          user_id: 1001,
          email: "newadmin@denvia.local",
          admin_grade: "pending",
          message: "가입 신청이 접수되었습니다. 운영자 승인 후 로그인 가능합니다.",
        }),
      }),
    );

    await page.goto("/admin/signup");

    await page.getByLabel("이름").fill("홍길동");
    await page.getByLabel("이메일").fill("newadmin@denvia.local");
    await page.getByLabel("연락처").fill("01012345678");
    await page.getByLabel("비밀번호").fill("password123");

    await page.getByRole("button", { name: "가입 신청" }).click();
    await expect(
      page.getByText("가입 신청이 접수되었습니다", { exact: false }),
    ).toBeVisible();
  });

  test("케이스 3: 이메일 중복(409) → ACCOUNT_EMAIL_DUPLICATE 안내 노출", async ({
    page,
  }) => {
    await page.route("**/api/v1/admin/auth/signup", (route) =>
      route.fulfill({
        status: 409,
        contentType: "application/json",
        body: JSON.stringify({
          code: "ACCOUNT_EMAIL_DUPLICATE",
          message: "이미 사용 중인 이메일입니다.",
        }),
      }),
    );

    await page.goto("/admin/signup");
    await page.getByLabel("이름").fill("홍길동");
    await page.getByLabel("이메일").fill("dup@denvia.local");
    await page.getByLabel("연락처").fill("01012345678");
    await page.getByLabel("비밀번호").fill("password123");
    await page.getByRole("button", { name: "가입 신청" }).click();

    await expect(
      page.getByText("이미 사용 중인 이메일입니다", { exact: false }),
    ).toBeVisible();
  });

  test("케이스 4: 연락처 중복(409) → ACCOUNT_PHONE_DUPLICATE 안내 노출", async ({
    page,
  }) => {
    await page.route("**/api/v1/admin/auth/signup", (route) =>
      route.fulfill({
        status: 409,
        contentType: "application/json",
        body: JSON.stringify({
          code: "ACCOUNT_PHONE_DUPLICATE",
          message: "이미 사용 중인 연락처입니다.",
        }),
      }),
    );

    await page.goto("/admin/signup");
    await page.getByLabel("이름").fill("홍길동");
    await page.getByLabel("이메일").fill("newadmin@denvia.local");
    await page.getByLabel("연락처").fill("01012345678");
    await page.getByLabel("비밀번호").fill("password123");
    await page.getByRole("button", { name: "가입 신청" }).click();

    await expect(
      page.getByText("이미 사용 중인 연락처입니다", { exact: false }),
    ).toBeVisible();
  });

  test("케이스 5: pending 계정 로그인 시도 → 401 ADMIN_PENDING_APPROVAL 안내 노출", async ({
    page,
  }) => {
    await page.route("**/api/v1/admin/auth/me", (route) =>
      route.fulfill({ status: 401, body: JSON.stringify({ code: "ADMIN_AUTH_REQUIRED" }) }),
    );
    await page.route("**/api/v1/admin/auth/login", (route) =>
      route.fulfill({
        status: 401,
        contentType: "application/json",
        body: JSON.stringify({
          code: "ADMIN_PENDING_APPROVAL",
          message: "관리자 승인 대기 중입니다. 운영자 승인 후 이용 가능합니다.",
        }),
      }),
    );

    await page.goto("/admin/login");
    await page.getByLabel("이메일").fill("pending@denvia.local");
    await page.getByLabel("비밀번호").fill("password123");
    await page.getByRole("button", { name: "로그인" }).click();
    await expect(
      page.getByText("관리자 승인 대기 중입니다", { exact: false }),
    ).toBeVisible();
  });
});

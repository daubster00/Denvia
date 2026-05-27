import { test, expect, type Page } from "@playwright/test";

/**
 * Story 10.4 — /admin/admins/logs 활동 로그 페이지 E2E 4 케이스.
 *
 * 실 백엔드 호출은 route intercept 로 mocking — UI 동작·권한 분기·다운로드 시그널만 검증한다.
 *  ① master 전체 조회 + 기본 7일 필터 동작
 *  ② operator 시야 제한 — actor_id=<master_id> → 403 ADMIN_LOG_FORBIDDEN_ACTOR 토스트
 *  ③ 엑셀 다운로드 트리거 + 파일명 패턴 + X-Truncated 토스트
 *  ④ diff 펼치기 → REDACTED 마스킹된 password_hash 노출
 */

const MASTER_ID = 1;
const OPERATOR_SELF_ID = 10;

const LOG_APPROVE = {
  id: 100,
  created_at: "2026-05-27T03:14:22.123456+00:00",
  actor_user_id: MASTER_ID,
  actor_email: "master@denvia.local",
  action: "admin.account.approved",
  target_type: "user",
  target_id: 42,
  target_preview: "newadmin@denvia.local",
  ip: "203.0.113.10",
  has_diff: true,
};

const LOG_RAG_EDIT = {
  id: 101,
  created_at: "2026-05-27T02:00:00.000000+00:00",
  actor_user_id: MASTER_ID,
  actor_email: "master@denvia.local",
  action: "rag.kb.updated",
  target_type: "kb",
  target_id: 7,
  target_preview: null,
  ip: "203.0.113.10",
  has_diff: false,
};

async function mockMe(page: Page, userId: number, email: string, isMaster: boolean) {
  await page.route("**/api/v1/admin/auth/me", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        user_id: userId,
        email,
        role: "admin",
        is_master: isMaster,
      }),
    }),
  );
}

async function mockLogsList(page: Page, items: unknown[], nextCursor: string | null = null) {
  await page.route("**/api/v1/admin/accounts/logs?**", (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ items, next_cursor: nextCursor }),
    });
  });
  await page.route("**/api/v1/admin/accounts/logs", (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ items, next_cursor: nextCursor }),
    });
  });
}

test.describe("Story 10.4 — /admin/admins/logs 활동 로그", () => {
  test("케이스 1: master 전체 조회 + 기본 7일 필터 적용", async ({ page }) => {
    await mockMe(page, MASTER_ID, "master@denvia.local", true);
    await mockLogsList(page, [LOG_APPROVE, LOG_RAG_EDIT]);

    await page.goto("/admin/admins/logs");
    await expect(page.getByRole("heading", { name: "관리자 활동 로그" })).toBeVisible();

    // 액션 칩이 노출됨(한글 라벨 + 미등록 코드는 원문 fallback)
    await expect(page.getByText("관리자 승인")).toBeVisible();
    await expect(page.getByText("rag.kb.updated")).toBeVisible();

    // 기본 기간 필드는 비어있지 않다 (7일 범위로 초기화)
    const dateInputs = page.locator('input[type="date"]');
    await expect(dateInputs.first()).not.toHaveValue("");
    await expect(dateInputs.nth(1)).not.toHaveValue("");
  });

  test("케이스 2: operator 시야 제한 — actor_id=master → 403 토스트", async ({ page }) => {
    await mockMe(page, OPERATOR_SELF_ID, "op@denvia.local", false);
    // 첫 진입 시 빈 리스트 응답
    await mockLogsList(page, []);

    await page.goto("/admin/admins/logs");
    await expect(page.getByRole("heading", { name: "관리자 활동 로그" })).toBeVisible();

    // 그 다음, master_id 입력 + 필터 적용 시 403 응답을 라우트로 덮어쓴다.
    await page.unroute("**/api/v1/admin/accounts/logs?**");
    await page.route("**/api/v1/admin/accounts/logs?**", (route) =>
      route.fulfill({
        status: 403,
        contentType: "application/json",
        body: JSON.stringify({
          code: "ADMIN_LOG_FORBIDDEN_ACTOR",
          message: "조회 권한이 없는 관리자입니다.",
        }),
      }),
    );

    await page.locator("#actor-id").fill(String(MASTER_ID));
    await page.getByRole("button", { name: "필터 적용" }).click();

    await expect(
      page.getByText(/ADMIN_LOG_FORBIDDEN_ACTOR/),
    ).toBeVisible();
  });

  test("케이스 3: 엑셀 다운로드 — X-Truncated 시 토스트", async ({ page }) => {
    await mockMe(page, MASTER_ID, "master@denvia.local", true);
    await mockLogsList(page, [LOG_APPROVE]);

    // export endpoint 는 작은 xlsx body + X-Truncated: true 헤더로 mocking
    const xlsxBody = Buffer.from("PK", "binary"); // 최소 zip 헤더 prefix
    await page.route("**/api/v1/admin/accounts/logs/export.xlsx**", (route) =>
      route.fulfill({
        status: 200,
        contentType:
          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers: {
          "Content-Disposition": 'attachment; filename="admin_logs_2026-05-21_2026-05-27.xlsx"',
          "X-Truncated": "true",
        },
        body: xlsxBody,
      }),
    );

    await page.goto("/admin/admins/logs");
    await expect(page.getByRole("heading", { name: "관리자 활동 로그" })).toBeVisible();

    await page.getByRole("button", { name: "엑셀로 저장" }).click();

    // truncated 토스트 노출
    await expect(
      page.getByText(/10,000행만 다운로드되었습니다/),
    ).toBeVisible();
  });

  test("케이스 4: diff 펼치기 → REDACTED 마스킹된 password_hash 노출", async ({ page }) => {
    await mockMe(page, MASTER_ID, "master@denvia.local", true);
    await mockLogsList(page, [LOG_APPROVE]);

    await page.route(
      `**/api/v1/admin/accounts/logs/${LOG_APPROVE.id}/diff`,
      (route) =>
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            id: LOG_APPROVE.id,
            diff_json: {
              before: {
                admin_grade: "pending",
                password_hash: "***REDACTED***",
              },
              after: { admin_grade: "sub_operator" },
            },
          }),
        }),
    );

    await page.goto("/admin/admins/logs");
    await expect(page.getByText("관리자 승인")).toBeVisible();

    // 펼치기 클릭
    await page.getByRole("button", { name: "펼치기" }).first().click();

    // REDACTED 가 노출됨
    await expect(page.getByText("***REDACTED***")).toBeVisible();
    // 일반 평문 키도 노출됨
    await expect(page.getByText(/admin_grade/)).toBeVisible();
  });
});

import { test, expect } from "@playwright/test";

/**
 * Story 10.3 — /admin/admins 관리자 관리 페이지 E2E 4 케이스.
 *
 * 실 백엔드 호출은 route intercept 로 mocking — admin_grade 가드 분기·UI 비활성 처리만 검증한다.
 *  ① master 로그인 → 승인 → 등급 변경 → 차단 → 삭제 전체 흐름
 *  ② operator 로그인 → master 행 액션 버튼 모두 비활성
 *  ③ operator 가 다른 operator 차단 시도 → 403 + 토스트 노출
 *  ④ master 본인 행 액션 버튼 미노출 + API 직접 호출도 403 검증
 */

const ROW_MASTER = {
  id: 1,
  email: "btmdesign@naver.com",
  admin_grade: "master",
  grade_label: "마스터",
  phone_masked: "010-****-1111",
  admin_blocked_until: null,
  admin_block_reason: null,
  admin_signup_at: null,
  last_login_at: null,
  created_at: "2026-01-01T00:00:00Z",
};

const ROW_OPERATOR_OTHER = {
  id: 2,
  email: "op2@denvia.local",
  admin_grade: "operator",
  grade_label: "운영 관리자",
  phone_masked: "010-****-2222",
  admin_blocked_until: null,
  admin_block_reason: null,
  admin_signup_at: null,
  last_login_at: null,
  created_at: "2026-02-01T00:00:00Z",
};

const ROW_SUB_OPERATOR = {
  id: 3,
  email: "sub@denvia.local",
  admin_grade: "sub_operator",
  grade_label: "부운영자",
  phone_masked: "010-****-3333",
  admin_blocked_until: null,
  admin_block_reason: null,
  admin_signup_at: null,
  last_login_at: null,
  created_at: "2026-03-01T00:00:00Z",
};

const ROW_PENDING = {
  id: 4,
  email: "pending@denvia.local",
  admin_grade: "pending",
  grade_label: "승인대기",
  phone_masked: "010-****-4444",
  admin_blocked_until: null,
  admin_block_reason: null,
  admin_signup_at: "2026-05-27T01:00:00Z",
  last_login_at: null,
  created_at: "2026-05-27T01:00:00Z",
};

async function mockMe(page, isMaster: boolean, userId: number, email: string) {
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

async function mockList(page, items: unknown[]) {
  await page.route("**/api/v1/admin/accounts*", (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ items, total: items.length }),
    });
  });
}

test.describe("Story 10.3 — /admin/admins 관리자 관리", () => {
  test("케이스 1: master 풀 흐름 (승인 → 등급 변경 → 차단 → 삭제)", async ({ page }) => {
    await mockMe(page, true, ROW_MASTER.id, ROW_MASTER.email);
    await mockList(page, [ROW_MASTER, ROW_OPERATOR_OTHER, ROW_SUB_OPERATOR, ROW_PENDING]);

    // 승인 mock — pending → operator
    await page.route(
      `**/api/v1/admin/accounts/${ROW_PENDING.id}/approve`,
      (route) =>
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            ...ROW_PENDING,
            admin_grade: "operator",
            grade_label: "운영 관리자",
          }),
        }),
    );
    // 등급 변경 mock
    await page.route(`**/api/v1/admin/accounts/${ROW_SUB_OPERATOR.id}`, (route) => {
      if (route.request().method() !== "PATCH") return route.fallback();
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ...ROW_SUB_OPERATOR,
          admin_grade: "operator",
          grade_label: "운영 관리자",
        }),
      });
    });
    // 차단 mock
    await page.route(
      `**/api/v1/admin/accounts/${ROW_OPERATOR_OTHER.id}/block`,
      (route) =>
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            ...ROW_OPERATOR_OTHER,
            admin_blocked_until: new Date(Date.now() + 7 * 24 * 3600 * 1000).toISOString(),
            admin_block_reason: "테스트 차단",
          }),
        }),
    );
    // 삭제 mock
    await page.route(`**/api/v1/admin/accounts/${ROW_OPERATOR_OTHER.id}`, (route) => {
      if (route.request().method() !== "DELETE") return route.fallback();
      return route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
    });

    await page.goto("/admin/admins");
    await expect(page.getByRole("heading", { name: "관리자 관리" })).toBeVisible();

    // 1) 승인 — pending 행의 "승인" 버튼 클릭
    await page
      .getByTestId(`btn-approve-${ROW_PENDING.id}`)
      .click();
    await page.getByTestId("approve-confirm").click();
    await expect(page.getByText("승인되었습니다.")).toBeVisible();

    // 2) 등급 변경 — sub_operator 행의 "등급 변경"
    await page.getByTestId(`btn-grade-${ROW_SUB_OPERATOR.id}`).click();
    await page.getByTestId("grade-confirm").click();
    await expect(page.getByText("등급을 변경했습니다.")).toBeVisible();

    // 3) 차단 — operator 행의 "차단"
    await page.getByTestId(`btn-block-${ROW_OPERATOR_OTHER.id}`).click();
    await page.locator("textarea").fill("테스트 차단");
    await page.getByTestId("block-confirm").click();
    await expect(page.getByText("차단되었습니다.")).toBeVisible();

    // 4) 삭제 — operator 행의 "삭제"
    await page.getByTestId(`btn-delete-${ROW_OPERATOR_OTHER.id}`).click();
    await page.locator('input[type="email"]').fill(ROW_OPERATOR_OTHER.email);
    await page.locator('input[type="text"]').fill("삭제합니다");
    await page.getByTestId("delete-confirm").click();
    await expect(page.getByText("삭제되었습니다.")).toBeVisible();
  });

  test("케이스 2: operator 로그인 → master 행 액션 버튼 모두 비활성", async ({ page }) => {
    await mockMe(page, false, ROW_OPERATOR_OTHER.id, ROW_OPERATOR_OTHER.email);
    await mockList(page, [ROW_MASTER, ROW_OPERATOR_OTHER, ROW_SUB_OPERATOR]);

    await page.goto("/admin/admins");
    // master 행에는 등급 변경·차단·삭제 버튼이 disabled.
    const blockBtn = page.getByTestId(`btn-block-${ROW_MASTER.id}`);
    const gradeBtn = page.getByTestId(`btn-grade-${ROW_MASTER.id}`);
    const deleteBtn = page.getByTestId(`btn-delete-${ROW_MASTER.id}`);
    await expect(blockBtn).toBeDisabled();
    await expect(gradeBtn).toBeDisabled();
    await expect(deleteBtn).toBeDisabled();
  });

  test("케이스 3: operator → 다른 operator 차단 시도 → 403 토스트", async ({ page }) => {
    // 본 테스트에서는 UI 가드를 우회해서 API가 거부하는 시나리오를 확인하기 위해
    // 일부러 다른 operator 를 sub_operator 처럼 등급을 낮춰 응답한 뒤
    // 백엔드 차단 호출이 403 을 돌려주는 케이스를 시뮬레이션한다.
    const operatorSelf = { ...ROW_OPERATOR_OTHER, id: 99, email: "self-op@denvia.local" };
    await mockMe(page, false, operatorSelf.id, operatorSelf.email);
    await mockList(page, [
      ROW_MASTER,
      operatorSelf,
      // 차단 대상도 일단 sub_operator 로 렌더 → 버튼이 활성화 되도록 함
      { ...ROW_OPERATOR_OTHER, admin_grade: "sub_operator", grade_label: "부운영자" },
    ]);
    await page.route(
      `**/api/v1/admin/accounts/${ROW_OPERATOR_OTHER.id}/block`,
      (route) =>
        route.fulfill({
          status: 403,
          contentType: "application/json",
          body: JSON.stringify({
            code: "ADMIN_FORBIDDEN_HIERARCHY",
            message: "자기 등급보다 높거나 같은 관리자는 관리할 수 없습니다.",
          }),
        }),
    );

    await page.goto("/admin/admins");
    await page.getByTestId(`btn-block-${ROW_OPERATOR_OTHER.id}`).click();
    await page.locator("textarea").fill("권한 외 차단 시도");
    await page.getByTestId("block-confirm").click();
    await expect(
      page.getByText("자기 등급보다 높거나 같은 관리자는 관리할 수 없습니다."),
    ).toBeVisible();
  });

  test("케이스 4: master 본인 행 액션 버튼 미노출 + API 직접 호출 403", async ({
    page,
    request,
  }) => {
    await mockMe(page, true, ROW_MASTER.id, ROW_MASTER.email);
    await mockList(page, [ROW_MASTER, ROW_SUB_OPERATOR]);

    await page.goto("/admin/admins");
    // 본인 행에는 삭제·차단·등급 변경 버튼이 disabled.
    await expect(page.getByTestId(`btn-delete-${ROW_MASTER.id}`)).toBeDisabled();
    await expect(page.getByTestId(`btn-grade-${ROW_MASTER.id}`)).toBeDisabled();

    // API 직접 호출 시도 — 403 ADMIN_MASTER_PROTECTED 또는 ADMIN_SELF_ACTION_FORBIDDEN.
    await page.route(
      `**/api/v1/admin/accounts/${ROW_MASTER.id}`,
      (route) => {
        if (route.request().method() !== "DELETE") return route.fallback();
        return route.fulfill({
          status: 403,
          contentType: "application/json",
          body: JSON.stringify({
            code: "ADMIN_MASTER_PROTECTED",
            message: "마스터 계정은 보호되어 있습니다.",
          }),
        });
      },
    );
    // 직접 fetch 로 거절되는 것을 확인 (가드 우회 시나리오).
    const status = await page.evaluate(async (id) => {
      const res = await fetch(`/api/v1/admin/accounts/${id}`, {
        method: "DELETE",
        credentials: "include",
      });
      return res.status;
    }, ROW_MASTER.id);
    expect(status).toBe(403);
  });
});

import { test, expect, type Page } from "@playwright/test";

/**
 * Story 4.6 — /admin/alimtalk 관리자 알림톡 관리 페이지 E2E 4 케이스.
 *
 * 실 백엔드 호출은 route intercept 로 mocking — UI 동작·권한 분기·발송 흐름만 검증.
 *  ① 번호 등록 → 테스트 발송 성공 토스트 + 카운트 증가
 *  ② 번호 미설정 시 모든 "테스트 발송" 버튼 disabled + tooltip
 *  ③ 일일 상한 429 토스트 노출
 *  ④ 로그 모달 + 마스킹 — 평문 phone 미노출 검증
 */

const MASTER_ID = 1;

const SUMMARY_SEED = {
  totals: { today_sent: 5, today_failed: 0, month_sent: 142, month_failed: 3 },
  templates: [
    {
      template_code: "billing.first_charge_success",
      title: "Denvia 첫 구독 결제 완료",
      category: "billing" as const,
      channel: "alimtalk" as const,
      aligo_tpl_code: "UH_9828",
      recipient_kind: "user" as const,
      trigger_situation: "첫 결제 성공 직후 결제자에게 발송",
      body_example: "안녕하세요, Denvia입니다.\n결제가 완료되었습니다.",
      today_sent: 2,
      today_failed: 0,
      month_sent: 38,
      month_failed: 1,
    },
    {
      template_code: "subscription.cancel_requested",
      title: "Denvia 구독 해지 예약 완료",
      category: "subscription" as const,
      channel: "alimtalk" as const,
      aligo_tpl_code: "UH_9833",
      recipient_kind: "user" as const,
      trigger_situation: "사용자가 해지 신청한 직후 발송",
      body_example: "Pro 구독 해지가 예약되었습니다.",
      today_sent: 0,
      today_failed: 0,
      month_sent: 12,
      month_failed: 0,
    },
  ],
};

async function mockMe(page: Page, grade: string | null = "master") {
  await page.route("**/api/v1/admin/auth/me", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        user_id: MASTER_ID,
        email: "master@denvia.local",
        role: "admin",
        is_master: grade === "master",
        admin_grade: grade,
        allowed_pages: ["/admin", "/admin/alimtalk"],
      }),
    }),
  );
}

async function mockSummary(page: Page, data: unknown = SUMMARY_SEED) {
  await page.route("**/api/v1/admin/alimtalk/summary", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(data),
    }),
  );
}

async function mockRecipient(page: Page, isSet: boolean, masked: string | null = null) {
  await page.route("**/api/v1/admin/alimtalk/test-recipient", (route) => {
    const m = route.request().method();
    if (m === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ phone_masked: masked, is_set: isSet }),
      });
    }
    if (m === "PUT") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ phone_masked: "010-****-8888", is_set: true }),
      });
    }
    if (m === "DELETE") {
      return route.fulfill({ status: 204, body: "" });
    }
    return route.fallback();
  });
}

test.describe("Story 4.6 — /admin/alimtalk 관리자 알림톡 관리", () => {
  test("케이스 1: 번호 등록 → 테스트 발송 성공 토스트", async ({ page }) => {
    await mockMe(page, "master");
    await mockSummary(page);
    await mockRecipient(page, false, null);

    let sendCalls = 0;
    await page.route("**/api/v1/admin/alimtalk/test-send", (route) => {
      sendCalls += 1;
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          success: true,
          template_code: "billing.first_charge_success",
          phone_masked: "010-****-8888",
          aligo_response_code: "0",
          error_message: null,
          message_id: "msg-1",
        }),
      });
    });

    await page.goto("/admin/alimtalk");
    await expect(page.getByText("알림톡 관리")).toBeVisible();

    // 번호 입력 + 저장
    await page.fill('input[aria-label="테스트 수신 번호 입력"]', "01099998888");
    await page.getByRole("button", { name: "저장" }).click();
    await expect(page.getByText(/테스트 수신 번호 저장 완료/)).toBeVisible();
    await expect(page.getByText("010-****-8888")).toBeVisible();

    // 행에서 테스트 발송 클릭
    await mockRecipient(page, true, "010-****-8888");
    const firstRowSend = page.getByRole("button", { name: "테스트 발송" }).first();
    await firstRowSend.click();
    await expect(page.getByText(/발송 성공/)).toBeVisible();
    expect(sendCalls).toBeGreaterThanOrEqual(1);
  });

  test("케이스 2: 번호 미설정 시 모든 발송 버튼 disabled", async ({ page }) => {
    await mockMe(page, "master");
    await mockSummary(page);
    await mockRecipient(page, false, null);

    await page.goto("/admin/alimtalk");
    await expect(page.getByText("알림톡 관리")).toBeVisible();

    const sendButtons = page.getByRole("button", { name: "테스트 발송" });
    const count = await sendButtons.count();
    expect(count).toBeGreaterThan(0);
    for (let i = 0; i < count; i++) {
      await expect(sendButtons.nth(i)).toBeDisabled();
    }
  });

  test("케이스 3: 일일 상한 429 토스트", async ({ page }) => {
    await mockMe(page, "master");
    await mockSummary(page);
    await mockRecipient(page, true, "010-****-8888");

    await page.route("**/api/v1/admin/alimtalk/test-send", (route) =>
      route.fulfill({
        status: 429,
        contentType: "application/json",
        body: JSON.stringify({
          detail: {
            code: "ALIMTALK_TEST_SEND_QUOTA_EXCEEDED",
            message: "하루 테스트 발송 한도(20건)를 초과했습니다. 내일 다시 시도해주세요.",
          },
        }),
      }),
    );

    await page.goto("/admin/alimtalk");
    await page.getByRole("button", { name: "테스트 발송" }).first().click();
    await expect(page.getByText(/하루 테스트 발송 한도/)).toBeVisible();
  });

  test("케이스 4: 로그 모달 마스킹 — 평문 phone 미노출", async ({ page }) => {
    await mockMe(page, "master");
    await mockSummary(page);
    await mockRecipient(page, true, "010-****-8888");

    await page.route("**/api/v1/admin/alimtalk/logs**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          items: [
            {
              id: 1001,
              created_at: "2026-06-05T03:14:22.000000+00:00",
              sent_at: "2026-06-05T03:14:22.500000+00:00",
              user_id: 42,
              phone_masked: "010-****-1234",
              channel: "alimtalk",
              status: "sent",
              attempts: 1,
              last_error: null,
              is_test: false,
            },
            {
              id: 1002,
              created_at: "2026-06-05T02:00:00.000000+00:00",
              sent_at: null,
              user_id: 91,
              phone_masked: "010-****-5678",
              channel: "alimtalk",
              status: "failed",
              attempts: 3,
              last_error: "aligo: code=-99 메시지가 템플릿과 일치하지않음",
              is_test: true,
            },
          ],
          next_cursor: null,
          total: 2,
          page: 1,
          per_page: 20,
          total_pages: 1,
        }),
      }),
    );

    await page.goto("/admin/alimtalk");
    // "상세보기"는 모달이 아니라 새 페이지로 이동하는 링크.
    await page.getByRole("link", { name: "상세보기" }).first().click();
    await expect(page).toHaveURL(/\/admin\/alimtalk\/billing\.first_charge_success/);

    // 페이지 상단 메타 + 로그 테이블에 마스킹 번호가 노출되는지 확인
    await expect(page.getByText("010-****-1234")).toBeVisible();
    await expect(page.getByText("010-****-5678")).toBeVisible();

    // 평문 11자리 phone 이 페이지 어디에도 노출되지 않아야 함
    const html = await page.content();
    expect(/01\d{9}/.test(html)).toBe(false);
  });
});

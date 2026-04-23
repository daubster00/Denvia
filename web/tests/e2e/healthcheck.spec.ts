import { test, expect } from "@playwright/test";

test.describe("헬스체크 E2E", () => {
  test("GET / → 200 + Denvia HTML 반환", async ({ page }) => {
    const response = await page.goto("http://localhost:3000/");
    expect(response?.status()).toBe(200);
    const content = await page.content();
    expect(content).toContain("Denvia");
  });

  test("GET /healthz → 200 + JSON {status:ok, db:up, redis:up}", async ({ request }) => {
    const response = await request.get("http://localhost:8000/healthz");
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body.status).toBe("ok");
    expect(body.db).toBe("up");
    expect(body.redis).toBe("up");
  });

  test("GET /readyz → 200 + JSON {status:ok}", async ({ request }) => {
    const response = await request.get("http://localhost:8000/readyz");
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body.status).toBe("ok");
  });
});

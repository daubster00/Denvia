import { describe, it, expect, beforeAll } from "vitest";
import { render, screen } from "@testing-library/react";
import { SignupsTrendChart } from "../SignupsTrendChart";
import type { SignupsResponse } from "../../api/analytics";

beforeAll(() => {
  // @ts-expect-error - jsdom polyfill
  global.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
});

function makeResponse(buckets: SignupsResponse["buckets"]): SignupsResponse {
  return { unit: "month", from: "2026-01-01", to: "2026-04-30", buckets };
}

describe("SignupsTrendChart", () => {
  it("4 series 라벨(누적/활성/신규/탈퇴) 렌더", () => {
    const data = makeResponse([
      { bucket_start: "2026-01-01", cumulative: 5, active: 4, withdrawn: 1, new_signups: 5 },
      { bucket_start: "2026-02-01", cumulative: 8, active: 6, withdrawn: 2, new_signups: 3 },
    ]);
    render(<SignupsTrendChart data={data} />);
    expect(screen.getAllByText("누적").length).toBeGreaterThan(0);
    expect(screen.getAllByText("활성").length).toBeGreaterThan(0);
    expect(screen.getAllByText("신규").length).toBeGreaterThan(0);
    expect(screen.getAllByText("탈퇴").length).toBeGreaterThan(0);
  });

  it("aria-label 동적 문구가 마지막 버킷 값을 반영", () => {
    const data = makeResponse([
      { bucket_start: "2026-01-01", cumulative: 1, active: 1, withdrawn: 0, new_signups: 1 },
      { bucket_start: "2026-02-01", cumulative: 7, active: 5, withdrawn: 2, new_signups: 6 },
    ]);
    render(<SignupsTrendChart data={data} />);
    const region = screen.getByRole("img");
    expect(region.getAttribute("aria-label")).toBe(
      "가입자 추세 — 누적 7, 활성 5, 신규 6, 탈퇴 2",
    );
  });

  it("buckets 비어있음 → EmptyState role=status 렌더", () => {
    const data = makeResponse([]);
    render(<SignupsTrendChart data={data} />);
    const status = screen.getByRole("status");
    expect(status.textContent).toMatch(/가입자 활동이 없습니다/);
  });

  it("모든 값 0 → EmptyState 렌더 (차트 미렌더)", () => {
    const data = makeResponse([
      { bucket_start: "2026-04-01", cumulative: 0, active: 0, withdrawn: 0, new_signups: 0 },
    ]);
    render(<SignupsTrendChart data={data} />);
    expect(screen.getByRole("status")).toBeTruthy();
  });

  it("KPICard 4개 — 마지막 버킷 값 표시", () => {
    const data = makeResponse([
      { bucket_start: "2026-01-01", cumulative: 100, active: 80, withdrawn: 20, new_signups: 12 },
    ]);
    render(<SignupsTrendChart data={data} />);
    expect(screen.getByText("100명")).toBeTruthy();
    expect(screen.getByText("80명")).toBeTruthy();
    expect(screen.getByText("12명")).toBeTruthy();
    expect(screen.getByText("20명")).toBeTruthy();
  });
});

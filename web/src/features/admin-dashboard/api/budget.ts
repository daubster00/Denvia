const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface BudgetCurrentMonth {
  year_month: string;
  monthly_limit_usd: string;
  spent_usd: string;
  // 전체 시스템 KRW 통일 — 응답 시점 환율로 환산된 보조 필드.
  monthly_limit_krw: number;
  spent_krw: number;
  usd_to_krw: number;
  percent: number;
  status: "normal" | "warning" | "critical";
  killswitch_active: boolean;
  killswitch_mode: "auto_free_only" | "manual_total" | null;
  // 지나간 달을 조회한 경우 true — 게이지/킬스위치 라벨 톤 변경에 사용.
  is_past_month: boolean;
}

export async function fetchBudgetCurrentMonth(
  ym?: string,
): Promise<BudgetCurrentMonth> {
  // React Query가 queryFn에 QueryFunctionContext를 자동 주입하기 때문에
  // queryFn 자리에 이 함수를 직접 넘기면 ym에 객체가 들어올 수 있다.
  // 문자열일 때만 ?ym=…을 붙여 422를 막는다.
  const url =
    typeof ym === "string" && ym.length > 0
      ? `${API_BASE}/api/v1/admin/budget/current-month?ym=${encodeURIComponent(ym)}`
      : `${API_BASE}/api/v1/admin/budget/current-month`;
  const res = await fetch(url, { credentials: "include" });
  if (!res.ok) throw new Error(`budget fetch failed: ${res.status}`);
  return res.json() as Promise<BudgetCurrentMonth>;
}

export async function updateMonthlyBudgetLimit(
  monthlyLimitUsd: number,
): Promise<BudgetCurrentMonth> {
  const res = await fetch(`${API_BASE}/api/v1/admin/budget/monthly-limit`, {
    method: "PATCH",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ monthly_limit_usd: monthlyLimitUsd }),
  });
  if (!res.ok) {
    let detail = `월 예산 한도 변경에 실패했습니다. (HTTP ${res.status})`;
    try {
      const body = (await res.json()) as { detail?: string | unknown };
      if (typeof body?.detail === "string") {
        detail = body.detail;
      }
    } catch {
      // ignore JSON parse error — keep default detail
    }
    throw new Error(detail);
  }
  return res.json() as Promise<BudgetCurrentMonth>;
}

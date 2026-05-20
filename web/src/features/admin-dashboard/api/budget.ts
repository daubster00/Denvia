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
}

export async function fetchBudgetCurrentMonth(): Promise<BudgetCurrentMonth> {
  const res = await fetch(`${API_BASE}/api/v1/admin/budget/current-month`, {
    credentials: "include",
  });
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

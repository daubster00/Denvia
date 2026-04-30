const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface BudgetCurrentMonth {
  year_month: string;
  monthly_limit_usd: string;
  spent_usd: string;
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

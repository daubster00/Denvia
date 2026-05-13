// Story 9.2 — Admin kill-switch API client.

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface AutoFreeOnlyStatus {
  active: boolean;
  activated_at: string | null;
  year_month: string | null;
  current_percent: number;
  monthly_limit_usd: string;
  spent_usd: string;
}

export interface ManualTotalStatus {
  active: boolean;
  activated_at: string | null;
  deactivated_at: string | null;
  reason: string | null;
  activated_by_admin_email: string | null;
  activated_by_admin_id: number | null;
}

export interface KillswitchStatusResponse {
  auto_free_only: AutoFreeOnlyStatus;
  manual_total: ManualTotalStatus;
}

export interface ManualActivateResponse {
  id: number;
  activated_at: string;
  mode: string;
  active: boolean;
}

export interface ManualDeactivateResponse {
  id: number;
  deactivated_at: string;
  duration_seconds: number;
  extension_task_id: string | null;
}

export class KillswitchApiError extends Error {
  code: string;
  status: number;
  constructor(code: string, message: string, status: number) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

async function parseJsonOrThrow<T>(res: Response): Promise<T> {
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const code = (body as { code?: string })?.code ?? "UNKNOWN_ERROR";
    const message = (body as { message?: string })?.message ?? `HTTP ${res.status}`;
    throw new KillswitchApiError(code, message, res.status);
  }
  return body as T;
}

export async function fetchKillswitchStatus(): Promise<KillswitchStatusResponse> {
  const res = await fetch(`${API_BASE}/api/v1/admin/killswitch/status`, {
    credentials: "include",
  });
  return parseJsonOrThrow<KillswitchStatusResponse>(res);
}

export async function activateManualKillswitch(
  reason: string,
): Promise<ManualActivateResponse> {
  const res = await fetch(
    `${API_BASE}/api/v1/admin/killswitch/manual/activate`,
    {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason }),
    },
  );
  return parseJsonOrThrow<ManualActivateResponse>(res);
}

export async function deactivateManualKillswitch(): Promise<ManualDeactivateResponse> {
  const res = await fetch(
    `${API_BASE}/api/v1/admin/killswitch/manual/deactivate`,
    {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
    },
  );
  return parseJsonOrThrow<ManualDeactivateResponse>(res);
}

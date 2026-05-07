import { z } from "zod";
import { ApiError } from "./popup";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const runtimeConfigFormSchema = z.object({
  show_subscribe_button: z.boolean(),
  free_daily_quota: z
    .number({ invalid_type_error: "숫자를 입력해주세요" })
    .int("정수만 입력 가능합니다")
    .min(0, "0 이상이어야 합니다")
    .max(9999, "9999 이하여야 합니다"),
  free_delay_enabled: z.boolean(),
  free_delay_seconds: z
    .number({ invalid_type_error: "숫자를 입력해주세요" })
    .int("정수만 입력 가능합니다")
    .min(0, "0 이상이어야 합니다")
    .max(30, "30 이하여야 합니다"),
});

export type RuntimeConfigFormInput = z.infer<typeof runtimeConfigFormSchema>;

export interface RuntimeConfigResponse {
  show_subscribe_button: boolean;
  free_daily_quota: number;
  free_delay_enabled: boolean;
  free_delay_seconds: number;
}

async function parseError(res: Response): Promise<ApiError> {
  let body: { code?: string; message?: string } = {};
  try {
    body = await res.json();
  } catch {
    // ignore
  }
  return new ApiError(
    body.message ?? `요청에 실패했습니다 (${res.status})`,
    res.status,
    body.code,
  );
}

export async function fetchRuntimeConfig(): Promise<RuntimeConfigResponse> {
  const res = await fetch(`${API_BASE}/api/v1/admin/runtime-config`, {
    credentials: "include",
  });
  if (!res.ok) throw await parseError(res);
  return res.json();
}

export async function updateRuntimeConfig(
  input: RuntimeConfigFormInput,
): Promise<RuntimeConfigResponse> {
  const res = await fetch(`${API_BASE}/api/v1/admin/runtime-config`, {
    method: "PUT",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!res.ok) throw await parseError(res);
  return res.json();
}

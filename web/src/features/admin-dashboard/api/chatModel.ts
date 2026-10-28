const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/**
 * 선택 가능한 모델 1종의 안내 정보 — 백엔드 카탈로그(SSOT)를 그대로 받는다.
 * 모델명·가격·설명을 프론트에 하드코딩하지 않는다. 가격 단위: USD / 100만 토큰.
 */
export interface ChatModelInfo {
  model_id: string;
  label: string;
  input_usd_per_mtok: number;
  output_usd_per_mtok: number;
  tier: string;
  speed: string;
  quality: string;
  note: string;
}

export interface ChatModelConfig {
  chat_model: string;
  allowed_models: string[];
  default_model: string;
  models: ChatModelInfo[];
}

/** "입력 $0.75 / 출력 $4.50 (100만 토큰당)" 형태의 가격 문구. */
export function formatModelPrice(m: ChatModelInfo): string {
  const f = (v: number) => `$${v.toFixed(2)}`;
  return `입력 ${f(m.input_usd_per_mtok)} / 출력 ${f(m.output_usd_per_mtok)} (100만 토큰당)`;
}

async function parseError(res: Response, fallback: string): Promise<Error> {
  let detail = `${fallback} (HTTP ${res.status})`;
  try {
    const body = (await res.json()) as { detail?: string | unknown; message?: string };
    if (typeof body?.detail === "string") {
      detail = body.detail;
    } else if (typeof body?.message === "string") {
      detail = body.message;
    }
  } catch {
    // ignore
  }
  return new Error(detail);
}

export async function fetchChatModelConfig(): Promise<ChatModelConfig> {
  const res = await fetch(`${API_BASE}/api/v1/admin/runtime-config/chat-model`, {
    credentials: "include",
  });
  if (!res.ok) throw await parseError(res, "AI 모델 설정을 불러오지 못했습니다");
  return res.json() as Promise<ChatModelConfig>;
}

export async function updateChatModelConfig(
  chatModel: string,
): Promise<ChatModelConfig> {
  const res = await fetch(`${API_BASE}/api/v1/admin/runtime-config/chat-model`, {
    method: "PUT",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_model: chatModel }),
  });
  if (!res.ok) throw await parseError(res, "AI 모델 변경에 실패했습니다");
  return res.json() as Promise<ChatModelConfig>;
}

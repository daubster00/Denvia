const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface ChatModelConfig {
  chat_model: string;
  allowed_models: string[];
  default_model: string;
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

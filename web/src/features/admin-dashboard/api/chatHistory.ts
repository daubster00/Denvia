import type { ChatModelInfo } from "./chatModel";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/**
 * 대화 이어가기(멀티턴) 설정 — 게시판 #149.
 *
 * 이전 대화를 GPT 에 함께 보내는 범위를 운영 중에 조정한다.
 * 모델 목록은 백엔드 카탈로그를 그대로 받아 쓴다(하드코딩 금지).
 */
export interface ChatHistoryConfig {
  enabled: boolean;
  max_turns: number;
  max_tokens: number;
  rewriter_model: string;
  models: ChatModelInfo[];
  default_max_turns: number;
  default_max_tokens: number;
}

export interface ChatHistoryConfigPayload {
  enabled: boolean;
  max_turns: number;
  max_tokens: number;
  rewriter_model: string;
}

async function parseError(res: Response, fallback: string): Promise<Error> {
  let detail = `${fallback} (HTTP ${res.status})`;
  try {
    const body = (await res.json()) as { detail?: unknown; message?: string };
    if (typeof body?.detail === "string") detail = body.detail;
    else if (typeof body?.message === "string") detail = body.message;
  } catch {
    // ignore
  }
  return new Error(detail);
}

export async function fetchChatHistoryConfig(): Promise<ChatHistoryConfig> {
  const res = await fetch(`${API_BASE}/api/v1/admin/runtime-config/chat-history`, {
    credentials: "include",
  });
  if (!res.ok) throw await parseError(res, "대화 이어가기 설정을 불러오지 못했습니다");
  return res.json() as Promise<ChatHistoryConfig>;
}

export async function updateChatHistoryConfig(
  payload: ChatHistoryConfigPayload,
): Promise<ChatHistoryConfig> {
  const res = await fetch(`${API_BASE}/api/v1/admin/runtime-config/chat-history`, {
    method: "PUT",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw await parseError(res, "대화 이어가기 설정 저장에 실패했습니다");
  return res.json() as Promise<ChatHistoryConfig>;
}

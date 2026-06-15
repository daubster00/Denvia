import { z } from "zod";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface PromptBlock {
  block_id: string;
  trigger_keywords: string[];
  content: string;
  enabled: boolean;
  updated_at: string;
}

export interface PromptsListResponse {
  blocks: PromptBlock[];
}

export interface ModelParamsResponse {
  rag_k: number;
  rag_temperature: number;
  max_tokens: number;
  /** 사용자 질문 입력 글자수 상한 (시스템 프롬프트 제외, 순수 질문만). */
  max_question_chars: number;
}

export const promptUpdateSchema = z.object({
  content: z.string().min(1, "내용을 입력하세요"),
  enabled: z.boolean(),
});

export const modelParamsSchema = z.object({
  rag_k: z.number().int().min(1, "최소 1 이상").max(20, "최대 20 이하"),
  rag_temperature: z.number().min(0, "최소 0.0 이상").max(1, "최대 1.0 이하"),
  max_tokens: z.number().int().min(256, "최소 256 이상").max(4096, "최대 4096 이하"),
  max_question_chars: z
    .number()
    .int()
    .min(100, "최소 100 이상")
    .max(5000, "최대 5000 이하"),
});

export type PromptUpdateInput = z.infer<typeof promptUpdateSchema>;
export type ModelParamsInput = z.infer<typeof modelParamsSchema>;

export async function fetchPrompts(): Promise<PromptsListResponse> {
  const res = await fetch(`${API_BASE}/api/v1/admin/rag/prompts`, { credentials: "include" });
  if (!res.ok) throw new Error("프롬프트 조회 실패");
  return res.json();
}

export async function updatePromptBlock(
  blockId: string,
  data: PromptUpdateInput,
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/v1/admin/rag/prompts/${encodeURIComponent(blockId)}`, {
    method: "PUT",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail?.code ?? err?.code ?? "저장 실패");
  }
}

export async function fetchModelParams(): Promise<ModelParamsResponse> {
  const res = await fetch(`${API_BASE}/api/v1/admin/rag/model-params`, { credentials: "include" });
  if (!res.ok) throw new Error("모델 파라미터 조회 실패");
  return res.json();
}

export async function updateModelParams(data: ModelParamsInput): Promise<void> {
  const res = await fetch(`${API_BASE}/api/v1/admin/rag/model-params`, {
    method: "PUT",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail?.code ?? err?.code ?? "저장 실패");
  }
}

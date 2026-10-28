import { z } from "zod";
import type { ChatModelInfo } from "@/features/admin-dashboard/api/chatModel";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** 모듈 발동조건(트리거 키워드). mode 별로 쓰는 리스트가 다르다. */
export type TriggerMode =
  | "base"
  | "keywords"
  | "keywords_all"
  | "keywords_combo"
  | "group";

export interface TriggerConfig {
  mode: TriggerMode;
  keywords?: string[];
  keywords_all?: string[];
  set1?: string[];
  independent?: string[];
  group_keywords?: string[];
  required_keywords?: string[];
}

export interface PromptBlock {
  block_id: string;
  trigger_keywords: string[];
  trigger_config?: TriggerConfig | null;
  content: string;
  enabled: boolean;
  updated_at: string;
  /** 상호배제(예외처리) — 이 블록이 켜지면 함께 숨길 블록 id 목록. */
  suppresses?: string[] | null;
  /** 원본(빌트인) 블록은 끄기만, 관리자 생성 블록만 완전 삭제 가능. */
  deletable: boolean;
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

/** 프롬프트 1개에 대한 모델 지정 1건. */
export interface PromptModelRouteItem {
  block_id: string;
  model: string;
  /** 지우지 않고 잠시 꺼둘 때 false. 꺼진 지정은 모델 선택에서 제외된다. */
  enabled: boolean;
}

/**
 * 특정 프롬프트 모델 지정 목록.
 *
 * 지정한 프롬프트 블록이 사용자 질문으로 실제 주입된 경우에만 그 모델이 쓰인다.
 * `routes` 순서가 곧 우선순위 — 한 질문에 지정 블록이 둘 이상 주입되면 앞쪽이 이긴다.
 * allowed_models / default_model 은 백엔드 화이트리스트를 그대로 받아 쓴다(하드코딩 금지).
 */
export interface PromptModelRoutes {
  routes: PromptModelRouteItem[];
  allowed_models: string[];
  default_model: string;
  /** 모델별 가격·설명 — 백엔드 카탈로그(SSOT). 지정 화면 드롭다운에 가격을 함께 보여준다. */
  models: ChatModelInfo[];
}

export interface PromptModelRoutesPayload {
  routes: PromptModelRouteItem[];
}

export async function fetchPromptModelRoutes(): Promise<PromptModelRoutes> {
  const res = await fetch(`${API_BASE}/api/v1/admin/rag/prompt-model-routes`, {
    credentials: "include",
  });
  if (!res.ok) throw new Error("특정 프롬프트 모델 설정 조회 실패");
  return res.json();
}

/** 저장 실패 시 백엔드 422 {code} 를 사람이 읽을 수 있는 문구로 바꿔 던진다. */
const ROUTE_ERROR_MESSAGES: Record<string, string> = {
  PROMPT_MODEL_ROUTE_BLOCK_REQUIRED: "대상 프롬프트를 선택하세요.",
  PROMPT_MODEL_ROUTE_MODEL_REQUIRED: "적용할 모델을 선택하세요.",
  PROMPT_MODEL_ROUTE_BLOCK_INVALID: "선택한 프롬프트를 사용할 수 없습니다.",
  PROMPT_MODEL_ROUTE_MODEL_INVALID: "선택한 모델을 사용할 수 없습니다.",
  PROMPT_MODEL_ROUTE_BLOCK_DUPLICATE:
    "같은 프롬프트를 두 번 지정할 수 없습니다. 프롬프트 1개당 모델 1개입니다.",
  PROMPT_MODEL_ROUTE_TOO_MANY: "지정이 너무 많습니다.",
};

export async function updatePromptModelRoutes(
  data: PromptModelRoutesPayload,
): Promise<PromptModelRoutes> {
  const res = await fetch(`${API_BASE}/api/v1/admin/rag/prompt-model-routes`, {
    method: "PUT",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const code = err?.detail?.code ?? err?.code;
    throw new Error(ROUTE_ERROR_MESSAGES[code] ?? code ?? "저장 실패");
  }
  return res.json();
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

/** PUT 페이로드 = 글 내용 + 켜기/끄기 + (선택) 발동조건 + (선택) 예외처리. */
export interface PromptUpdatePayload {
  content: string;
  enabled: boolean;
  trigger_config?: TriggerConfig | null;
  suppresses?: string[] | null;
}

export async function fetchPrompts(): Promise<PromptsListResponse> {
  const res = await fetch(`${API_BASE}/api/v1/admin/rag/prompts`, { credentials: "include" });
  if (!res.ok) throw new Error("프롬프트 조회 실패");
  return res.json();
}

export async function updatePromptBlock(
  blockId: string,
  data: PromptUpdatePayload,
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

/** POST 페이로드 = 블록 이름 + 내용 + 켜기/끄기 + 발동조건(필수). */
export interface PromptCreatePayload {
  block_id: string;
  content: string;
  enabled: boolean;
  trigger_config: TriggerConfig;
  suppresses?: string[] | null;
}

export async function createPromptBlock(data: PromptCreatePayload): Promise<void> {
  const res = await fetch(`${API_BASE}/api/v1/admin/rag/prompts`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail?.code ?? err?.code ?? "생성 실패");
  }
}

export async function deletePromptBlock(blockId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/v1/admin/rag/prompts/${encodeURIComponent(blockId)}`, {
    method: "DELETE",
    credentials: "include",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail?.code ?? err?.code ?? "삭제 실패");
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

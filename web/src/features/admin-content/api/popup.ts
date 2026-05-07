import { z } from "zod";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ──────────────────────────────────────────────────────────────────────────────
// zod 스키마 — Story 7.2 v2 (백엔드 Pydantic과 1:1)
// ──────────────────────────────────────────────────────────────────────────────

export const popupFormSchema = z
  .object({
    title: z
      .string()
      .min(1, "제목을 입력해주세요")
      .max(200, "제목은 200자 이내"),
    popup_type: z.enum(["image", "editor"]),
    target_device: z.enum(["pc", "mobile", "both"]),
    body_html: z
      .string()
      .max(20000, "본문이 너무 깁니다")
      .optional()
      .or(z.literal("")),
    image_url: z.string().max(500).optional().or(z.literal("")),
    link_url: z
      .string()
      .max(500)
      .regex(/^https?:\/\//i, "https:// 또는 http://로 시작하는 URL")
      .optional()
      .or(z.literal("")),
    display_start: z.string().min(1, "노출 시작 시각을 입력해주세요"),
    display_end: z.string().min(1, "노출 종료 시각을 입력해주세요"),
    target_segment: z.enum(["all", "doctor", "hygienist", "student_other"]),
    sort_order: z
      .number()
      .int()
      .min(0, "0 이상")
      .max(999, "999 이하"),
    is_active: z.boolean(),
  })
  .refine(
    (data) => new Date(data.display_end) > new Date(data.display_start),
    {
      message: "종료일은 시작일보다 늦어야 합니다",
      path: ["display_end"],
    },
  )
  .refine(
    (data) =>
      data.popup_type !== "image" || (data.image_url && data.image_url !== ""),
    {
      message: "이미지를 업로드해주세요",
      path: ["image_url"],
    },
  )
  .refine(
    (data) =>
      data.popup_type !== "editor" ||
      (data.body_html && data.body_html.trim() !== ""),
    {
      message: "본문을 입력해주세요",
      path: ["body_html"],
    },
  );

export type PopupFormInput = z.infer<typeof popupFormSchema>;

export type TargetSegment = "all" | "doctor" | "hygienist" | "student_other";
export type TargetDevice = "pc" | "mobile" | "both";
export type PopupType = "image" | "editor";

export interface PopupListItem {
  id: number;
  title: string;
  display_start: string;
  display_end: string;
  target_segment: TargetSegment;
  target_device: TargetDevice;
  popup_type: PopupType;
  image_url: string | null;
  sort_order: number;
  is_active: boolean;
  link_url: string | null;
  created_by_admin_id: number;
  created_at: string;
  updated_at: string;
}

export interface PopupDetail extends PopupListItem {
  body_html: string | null;
}

export interface PopupListResponse {
  items: PopupListItem[];
  page: number;
  per_page: number;
  total: number;
}

export interface PopupToggleResponse {
  id: number;
  is_active: boolean;
  updated_at: string;
}

export interface PopupImageUploadResponse {
  image_url: string;
  size_bytes: number;
  mime_type: string;
}

// ──────────────────────────────────────────────────────────────────────────────
// fetcher
// ──────────────────────────────────────────────────────────────────────────────

class ApiError extends Error {
  code?: string;
  status: number;
  constructor(message: string, status: number, code?: string) {
    super(message);
    this.code = code;
    this.status = status;
  }
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

export async function fetchPopups(
  page = 1,
  perPage = 20,
): Promise<PopupListResponse> {
  const url = `${API_BASE}/api/v1/admin/popups?page=${page}&per_page=${perPage}`;
  const res = await fetch(url, { credentials: "include" });
  if (!res.ok) throw await parseError(res);
  return res.json();
}

export async function fetchPopupDetail(id: number): Promise<PopupDetail> {
  const res = await fetch(`${API_BASE}/api/v1/admin/popups/${id}`, {
    credentials: "include",
  });
  if (!res.ok) throw await parseError(res);
  return res.json();
}

function toRequestBody(input: PopupFormInput) {
  const body_html =
    input.popup_type === "editor"
      ? input.body_html && input.body_html !== ""
        ? input.body_html
        : null
      : null;
  const image_url =
    input.popup_type === "image"
      ? input.image_url && input.image_url !== ""
        ? input.image_url
        : null
      : null;
  return {
    title: input.title,
    popup_type: input.popup_type,
    target_device: input.target_device,
    body_html,
    image_url,
    link_url: input.link_url === "" ? null : (input.link_url ?? null),
    display_start: new Date(input.display_start).toISOString(),
    display_end: new Date(input.display_end).toISOString(),
    target_segment: input.target_segment,
    sort_order: input.sort_order,
    is_active: input.is_active,
  };
}

export async function createPopup(
  input: PopupFormInput,
): Promise<PopupDetail> {
  const res = await fetch(`${API_BASE}/api/v1/admin/popups`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(toRequestBody(input)),
  });
  if (!res.ok) throw await parseError(res);
  return res.json();
}

export async function updatePopup(
  id: number,
  input: PopupFormInput,
): Promise<PopupDetail> {
  const res = await fetch(`${API_BASE}/api/v1/admin/popups/${id}`, {
    method: "PUT",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(toRequestBody(input)),
  });
  if (!res.ok) throw await parseError(res);
  return res.json();
}

export async function togglePopupActive(
  id: number,
  isActive: boolean,
): Promise<PopupToggleResponse> {
  const res = await fetch(`${API_BASE}/api/v1/admin/popups/${id}`, {
    method: "PATCH",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ is_active: isActive }),
  });
  if (!res.ok) throw await parseError(res);
  return res.json();
}

export async function deletePopup(id: number): Promise<void> {
  const res = await fetch(`${API_BASE}/api/v1/admin/popups/${id}`, {
    method: "DELETE",
    credentials: "include",
  });
  if (!res.ok) throw await parseError(res);
}

export async function uploadPopupImage(
  file: File,
): Promise<PopupImageUploadResponse> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API_BASE}/api/v1/admin/popups/image-upload`, {
    method: "POST",
    credentials: "include",
    body: formData,
  });
  if (!res.ok) throw await parseError(res);
  return res.json();
}

export { ApiError };

/**
 * 관리자 수정요청 게시판 API 클라이언트.
 *
 * 백엔드: api/src/routers/admin/board.py
 * 인증: denvia_admin_session 쿠키 (credentials: "include" 필수)
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type BoardPostStatus =
  | "review"
  | "in_progress"
  | "completed"
  | "rejected"
  | "on_hold"
  | "confirm_requested"
  | "confirmed";

// 신규 4종. 응답에는 과거 글의 레거시 키(auth 등)가 섞일 수 있어 string 으로도 받는다.
export type BoardCategory = "error" | "feature" | "inquiry" | "etc";

export interface BoardAttachment {
  id: number;
  file_url: string;
  file_name: string;
  mime_type: string;
  size_bytes: number;
}

export interface BoardAttachmentRef {
  file_url: string;
  file_name: string;
  mime_type: string;
  size_bytes: number;
}

export interface BoardPostListItem {
  id: number;
  category: string;
  status: BoardPostStatus;
  title: string;
  author_id: number;
  author_email: string;
  author_display: string;
  comment_count: number;
  has_attachments: boolean;
  created_at: string;
  updated_at: string;
}

export interface BoardPostListResponse {
  items: BoardPostListItem[];
  page: number;
  per_page: number;
  total: number;
}

export interface BoardCommentItem {
  id: number;
  post_id: number;
  author_id: number;
  author_email: string;
  author_display: string;
  content: string;
  created_at: string;
  updated_at: string;
  can_edit: boolean;
}

export interface BoardPostDetail {
  id: number;
  category: string;
  status: BoardPostStatus;
  title: string;
  content_html: string;
  author_id: number;
  author_email: string;
  author_display: string;
  comments: BoardCommentItem[];
  attachments: BoardAttachment[];
  dev_cost: number | null;
  can_edit: boolean;
  can_change_status: boolean;
  can_set_dev_cost: boolean;
  can_confirm: boolean;
  created_at: string;
  updated_at: string;
}

export interface BoardMeta {
  categories: { key: BoardCategory; label: string }[];
  statuses: { key: BoardPostStatus; label: string }[];
}

export interface BoardImageUploadResponse {
  file_url: string;
  file_name: string;
  mime_type: string;
  size_bytes: number;
}

export interface BoardAttachmentUploadResponse {
  file_url: string;
  file_name: string;
  mime_type: string;
  size_bytes: number;
}

export interface BoardPostFormInput {
  category: BoardCategory;
  title: string;
  content_html: string;
  attachments: BoardAttachmentRef[];
}

export class BoardApiError extends Error {
  code?: string;
  status: number;
  constructor(message: string, status: number, code?: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function parseError(res: Response): Promise<BoardApiError> {
  let body: { code?: string; message?: string } = {};
  try {
    body = await res.json();
  } catch {
    // ignore
  }
  return new BoardApiError(
    body.message ?? `요청에 실패했습니다 (${res.status})`,
    res.status,
    body.code,
  );
}

// ── 메타 ──────────────────────────────────────────────────────────────────────
export async function fetchBoardMeta(): Promise<BoardMeta> {
  const res = await fetch(`${API_BASE}/api/v1/admin/board/meta`, {
    credentials: "include",
  });
  if (!res.ok) throw await parseError(res);
  return res.json();
}

// ── 글 ────────────────────────────────────────────────────────────────────────
export async function fetchBoardPosts(params: {
  category?: BoardCategory | "";
  status?: BoardPostStatus | "";
  page?: number;
  per_page?: number;
}): Promise<BoardPostListResponse> {
  const query = new URLSearchParams();
  if (params.category) query.set("category", params.category);
  if (params.status) query.set("status", params.status);
  query.set("page", String(params.page ?? 1));
  query.set("per_page", String(params.per_page ?? 20));
  const res = await fetch(
    `${API_BASE}/api/v1/admin/board/posts?${query.toString()}`,
    { credentials: "include" },
  );
  if (!res.ok) throw await parseError(res);
  return res.json();
}

export async function fetchBoardPost(postId: number): Promise<BoardPostDetail> {
  const res = await fetch(
    `${API_BASE}/api/v1/admin/board/posts/${postId}`,
    { credentials: "include" },
  );
  if (!res.ok) throw await parseError(res);
  return res.json();
}

export async function createBoardPost(
  input: BoardPostFormInput,
): Promise<BoardPostDetail> {
  const res = await fetch(`${API_BASE}/api/v1/admin/board/posts`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!res.ok) throw await parseError(res);
  return res.json();
}

export async function updateBoardPost(
  postId: number,
  input: BoardPostFormInput,
): Promise<BoardPostDetail> {
  const res = await fetch(`${API_BASE}/api/v1/admin/board/posts/${postId}`, {
    method: "PUT",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!res.ok) throw await parseError(res);
  return res.json();
}

export async function updateBoardPostStatus(
  postId: number,
  status: BoardPostStatus,
): Promise<BoardPostDetail> {
  const res = await fetch(
    `${API_BASE}/api/v1/admin/board/posts/${postId}/status`,
    {
      method: "PATCH",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    },
  );
  if (!res.ok) throw await parseError(res);
  return res.json();
}

// 추가개발비 입력 — 마스터 전용. 저장 시 상태가 "컨펌요청"으로 바뀐다.
export async function setBoardDevCost(
  postId: number,
  devCost: number,
): Promise<BoardPostDetail> {
  const res = await fetch(
    `${API_BASE}/api/v1/admin/board/posts/${postId}/dev-cost`,
    {
      method: "PATCH",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dev_cost: devCost }),
    },
  );
  if (!res.ok) throw await parseError(res);
  return res.json();
}

// 추가개발비 컨펌 — 운영자 전용. 상태가 "컨펌요청" → "컨펌"으로 바뀐다.
export async function confirmBoardPost(
  postId: number,
): Promise<BoardPostDetail> {
  const res = await fetch(
    `${API_BASE}/api/v1/admin/board/posts/${postId}/confirm`,
    { method: "POST", credentials: "include" },
  );
  if (!res.ok) throw await parseError(res);
  return res.json();
}

export async function deleteBoardPost(postId: number): Promise<void> {
  const res = await fetch(`${API_BASE}/api/v1/admin/board/posts/${postId}`, {
    method: "DELETE",
    credentials: "include",
  });
  if (!res.ok) throw await parseError(res);
}

// ── 댓글 ─────────────────────────────────────────────────────────────────────
export async function createBoardComment(
  postId: number,
  content: string,
): Promise<BoardPostDetail> {
  const res = await fetch(
    `${API_BASE}/api/v1/admin/board/posts/${postId}/comments`,
    {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content }),
    },
  );
  if (!res.ok) throw await parseError(res);
  return res.json();
}

export async function updateBoardComment(
  commentId: number,
  content: string,
): Promise<void> {
  const res = await fetch(
    `${API_BASE}/api/v1/admin/board/comments/${commentId}`,
    {
      method: "PUT",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content }),
    },
  );
  if (!res.ok) throw await parseError(res);
}

export async function deleteBoardComment(commentId: number): Promise<void> {
  const res = await fetch(
    `${API_BASE}/api/v1/admin/board/comments/${commentId}`,
    { method: "DELETE", credentials: "include" },
  );
  if (!res.ok) throw await parseError(res);
}

// ── 이미지 업로드 ─────────────────────────────────────────────────────────────
export async function uploadBoardImage(
  file: File,
): Promise<BoardImageUploadResponse> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API_BASE}/api/v1/admin/board/image-upload`, {
    method: "POST",
    credentials: "include",
    body: formData,
  });
  if (!res.ok) throw await parseError(res);
  return res.json();
}

// ── 첨부 파일 업로드 ─────────────────────────────────────────────────────────
export async function uploadBoardAttachment(
  file: File,
): Promise<BoardAttachmentUploadResponse> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API_BASE}/api/v1/admin/board/attachment-upload`, {
    method: "POST",
    credentials: "include",
    body: formData,
  });
  if (!res.ok) throw await parseError(res);
  return res.json();
}

// 첨부 허용 확장자 — 프론트 1차 검증 및 <input accept> 용.
export const BOARD_ATTACHMENT_ACCEPT =
  ".pdf,.zip,.doc,.docx,.hwp,.hwpx,.xls,.xlsx,.ppt,.pptx,.txt,.csv,image/*";
export const BOARD_MAX_ATTACHMENTS = 10;
export const BOARD_MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024;

const BOARD_ALLOWED_EXTS = new Set([
  "pdf", "txt", "csv", "doc", "docx", "hwp", "hwpx",
  "xls", "xlsx", "ppt", "pptx", "zip",
  "png", "jpg", "jpeg", "gif", "webp", "bmp",
  "svg", "tif", "tiff", "heic", "heif", "ico",
]);

export function isBoardAttachmentAllowed(fileName: string): boolean {
  const dot = fileName.lastIndexOf(".");
  if (dot < 0) return false;
  return BOARD_ALLOWED_EXTS.has(fileName.slice(dot + 1).toLowerCase());
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

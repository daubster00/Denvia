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
  | "on_hold";

export type BoardCategory =
  | "auth"
  | "mypage"
  | "chatbot"
  | "billing"
  | "admin"
  | "messaging"
  | "design"
  | "etc";

export interface BoardPostListItem {
  id: number;
  category: BoardCategory;
  status: BoardPostStatus;
  title: string;
  author_id: number;
  author_email: string;
  author_display: string;
  comment_count: number;
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
  category: BoardCategory;
  status: BoardPostStatus;
  title: string;
  content_html: string;
  author_id: number;
  author_email: string;
  author_display: string;
  comments: BoardCommentItem[];
  can_edit: boolean;
  can_change_status: boolean;
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

export interface BoardPostFormInput {
  category: BoardCategory;
  title: string;
  content_html: string;
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

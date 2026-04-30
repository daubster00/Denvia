const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface HierarchyPreviewItem {
  major: string;
  minors: string[];
}

export interface UploadKnowledgeResponse {
  upload_id: number;
  filename: string;
  size_bytes: number;
  chunk_count: number;
  category_count: number;
  hierarchy_preview: HierarchyPreviewItem[];
}

export interface KnowledgeListItem {
  id: number;
  filename: string;
  uploaded_at: string;
  size_bytes: number;
  chunk_count: number | null;
  category_count: number | null;
  status: string;
  uploaded_by_admin_id: number;
}

export interface KnowledgeListResponse {
  items: KnowledgeListItem[];
  page: number;
  per_page: number;
  total: number;
}

export function uploadKnowledge(
  file: File,
  onProgress: (pct: number) => void,
): Promise<UploadKnowledgeResponse> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE}/api/v1/admin/rag/knowledge/upload`);
    xhr.withCredentials = true;
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) {
        onProgress((e.loaded / e.total) * 100);
      }
    };
    xhr.onload = () => {
      const body = (() => {
        try {
          return JSON.parse(xhr.responseText);
        } catch {
          return {};
        }
      })();
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(body as UploadKnowledgeResponse);
      } else {
        const err = new Error(body?.message ?? `upload failed: ${xhr.status}`);
        (err as { code?: string }).code = body?.code;
        (err as { status?: number }).status = xhr.status;
        (err as { details?: unknown }).details = body?.details ?? body;
        reject(err);
      }
    };
    xhr.onerror = () => reject(new Error("network_error"));
    const fd = new FormData();
    fd.append("file", file);
    xhr.send(fd);
  });
}

export async function fetchKnowledgeList(
  page: number,
  perPage: number,
): Promise<KnowledgeListResponse> {
  const res = await fetch(
    `${API_BASE}/api/v1/admin/rag/knowledge?page=${page}&per_page=${perPage}`,
    { credentials: "include" },
  );
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.message ?? `fetch failed: ${res.status}`);
  }
  return res.json();
}

export interface KnowledgeDetailResponse {
  id: number;
  filename: string;
  uploaded_at: string;
  last_modified_at: string;
  size_bytes: number;
  chunk_count: number | null;
  category_count: number | null;
  status: string;
  content: string;
}

export interface KnowledgeEditResponse {
  id: number;
  filename: string;
  size_bytes: number;
  chunk_count: number;
  category_count: number;
  status: string;
  last_modified_at: string;
}

export interface ActiveRebuildInfo {
  job_id: number;
  status: string;
  progress_percent: number;
  stage: string | null;
}

export interface RagStatusResponse {
  pending_changes_count: number;
  last_rebuild_at: string | null;
  last_rebuild_status: string | null;
  active_rebuild: ActiveRebuildInfo | null;
}

export interface RebuildTriggerResponse {
  job_id: number;
  target_slot: string;
}

export interface RebuildJobStatusResponse {
  id: number;
  status: string;
  progress_percent: number;
  stage: string | null;
  target_slot: string;
  started_at: string | null;
  finished_at: string | null;
  swapped_at: string | null;
  chunk_count_after: number | null;
  error_message: string | null;
}

export async function fetchKnowledgeDetail(id: number): Promise<KnowledgeDetailResponse> {
  const res = await fetch(`${API_BASE}/api/v1/admin/rag/knowledge/${id}`, {
    credentials: "include",
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.message ?? `fetch failed: ${res.status}`);
  }
  return res.json();
}

export async function editKnowledge(id: number, content: string): Promise<KnowledgeEditResponse> {
  const res = await fetch(`${API_BASE}/api/v1/admin/rag/knowledge/${id}`, {
    method: "PUT",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const err = new Error(body?.message ?? `edit failed: ${res.status}`);
    (err as { code?: string }).code = body?.code;
    throw err;
  }
  return res.json();
}

export async function deleteKnowledge(id: number): Promise<void> {
  const res = await fetch(`${API_BASE}/api/v1/admin/rag/knowledge/${id}`, {
    method: "DELETE",
    credentials: "include",
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.message ?? `delete failed: ${res.status}`);
  }
}

export async function fetchRagStatus(): Promise<RagStatusResponse> {
  const res = await fetch(`${API_BASE}/api/v1/admin/rag/status`, {
    credentials: "include",
  });
  if (!res.ok) throw new Error(`rag status fetch failed: ${res.status}`);
  return res.json();
}

export async function triggerRebuild(): Promise<RebuildTriggerResponse> {
  const res = await fetch(`${API_BASE}/api/v1/admin/rag/rebuild`, {
    method: "POST",
    credentials: "include",
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const err = new Error(body?.message ?? `trigger rebuild failed: ${res.status}`);
    (err as { code?: string }).code = body?.code;
    (err as { status?: number }).status = res.status;
    throw err;
  }
  return res.json();
}

export async function cancelRebuild(jobId: number): Promise<RebuildJobStatusResponse> {
  const res = await fetch(`${API_BASE}/api/v1/admin/rag/rebuild/${jobId}/cancel`, {
    method: "POST",
    credentials: "include",
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.message ?? `cancel rebuild failed: ${res.status}`);
  }
  return res.json();
}

export async function fetchRebuildJob(jobId: number): Promise<RebuildJobStatusResponse> {
  const res = await fetch(`${API_BASE}/api/v1/admin/rag/rebuild/${jobId}`, {
    credentials: "include",
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.message ?? `fetch rebuild job failed: ${res.status}`);
  }
  return res.json();
}

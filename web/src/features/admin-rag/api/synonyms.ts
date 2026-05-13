import { z } from "zod";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface SynonymGroup {
  id: number;
  canonical_term: string;
  synonyms: string[];
  updated_at: string;
}

export interface SynonymListResponse {
  groups: SynonymGroup[];
  total: number;
  page: number;
  size: number;
}

export interface ImportSummary {
  to_create: number;
  to_update: number;
  conflicts: number;
  invalid: number;
  unchanged: number;
}

export interface ImportConflict {
  row: number;
  canonical_term: string;
  reason: string;
}

export interface ImportInvalidRow {
  row: number;
  error: string;
}

export interface ImportPreviewResponse {
  summary: ImportSummary;
  conflicts: ImportConflict[];
  invalid: ImportInvalidRow[];
}

export const synonymGroupSchema = z.object({
  canonical_term: z.string().trim().min(1, "대표어를 입력하세요").max(100, "100자 이내"),
  synonyms: z
    .array(z.string().trim().min(1).max(100))
    .max(50, "동의어는 최대 50개까지 가능합니다"),
});

export type SynonymGroupInput = z.infer<typeof synonymGroupSchema>;

async function readErrorCode(res: Response, fallback: string): Promise<string> {
  try {
    const body = await res.json();
    return body?.code ?? body?.detail?.code ?? fallback;
  } catch {
    return fallback;
  }
}

export async function fetchSynonyms(params: {
  q?: string;
  page?: number;
  size?: number;
}): Promise<SynonymListResponse> {
  const sp = new URLSearchParams();
  if (params.q) sp.set("q", params.q);
  if (params.page) sp.set("page", String(params.page));
  if (params.size) sp.set("size", String(params.size));

  const url = `${API_BASE}/api/v1/admin/rag/synonyms${sp.toString() ? `?${sp}` : ""}`;
  const res = await fetch(url, { credentials: "include" });
  if (!res.ok) throw new Error(await readErrorCode(res, "SYNONYMS_FETCH_FAILED"));
  return res.json();
}

export async function createSynonymGroup(data: SynonymGroupInput): Promise<SynonymGroup> {
  const res = await fetch(`${API_BASE}/api/v1/admin/rag/synonyms`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(await readErrorCode(res, "SYNONYM_CREATE_FAILED"));
  return res.json();
}

export async function updateSynonymGroup(
  id: number,
  data: SynonymGroupInput,
): Promise<SynonymGroup> {
  const res = await fetch(`${API_BASE}/api/v1/admin/rag/synonyms/${id}`, {
    method: "PUT",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(await readErrorCode(res, "SYNONYM_UPDATE_FAILED"));
  return res.json();
}

export async function deleteSynonymGroup(id: number): Promise<void> {
  const res = await fetch(`${API_BASE}/api/v1/admin/rag/synonyms/${id}`, {
    method: "DELETE",
    credentials: "include",
  });
  if (!res.ok && res.status !== 204) {
    throw new Error(await readErrorCode(res, "SYNONYM_DELETE_FAILED"));
  }
}

export async function importSynonymCsv(
  file: File,
  dryRun: boolean,
): Promise<ImportPreviewResponse> {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch(
    `${API_BASE}/api/v1/admin/rag/synonyms/import?dry_run=${dryRun ? "true" : "false"}`,
    {
      method: "POST",
      credentials: "include",
      body: fd,
    },
  );
  if (!res.ok) {
    if (res.status === 409) {
      const body = await res.json().catch(() => ({}));
      const err = new Error("IMPORT_HAS_CONFLICTS") as Error & {
        summary?: ImportSummary;
        conflicts?: ImportConflict[];
      };
      err.summary = body?.details?.summary;
      err.conflicts = body?.details?.conflicts;
      throw err;
    }
    throw new Error(await readErrorCode(res, "SYNONYM_IMPORT_FAILED"));
  }
  return res.json();
}

export function buildExportUrl(): string {
  return `${API_BASE}/api/v1/admin/rag/synonyms/export`;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface SeoConfig {
  site_name: string;
  site_description: string;
  keywords: string;
  og_image_url: string;
  favicon_url: string;
  default_site_name: string;
  default_site_description: string;
  default_keywords: string;
  default_og_image_url: string;
  default_favicon_url: string;
}

export interface SeoConfigUpdateInput {
  site_name: string;
  site_description: string;
  keywords: string;
  og_image_url: string;
  favicon_url: string;
}

export interface SeoAssetUploadResult {
  asset_url: string;
  kind: "favicon" | "og_image";
}

async function parseError(res: Response, fallback: string): Promise<Error> {
  let detail = `${fallback} (HTTP ${res.status})`;
  try {
    const body = (await res.json()) as {
      detail?: string | { message?: string } | unknown;
      message?: string;
    };
    if (typeof body?.detail === "string") {
      detail = body.detail;
    } else if (
      body?.detail &&
      typeof body.detail === "object" &&
      "message" in (body.detail as Record<string, unknown>) &&
      typeof (body.detail as { message?: unknown }).message === "string"
    ) {
      detail = (body.detail as { message: string }).message;
    } else if (typeof body?.message === "string") {
      detail = body.message;
    }
  } catch {
    // ignore
  }
  return new Error(detail);
}

export async function fetchSeoConfig(): Promise<SeoConfig> {
  const res = await fetch(`${API_BASE}/api/v1/admin/seo-config`, {
    credentials: "include",
  });
  if (!res.ok) throw await parseError(res, "SEO 설정을 불러오지 못했습니다");
  return res.json() as Promise<SeoConfig>;
}

export async function updateSeoConfig(
  input: SeoConfigUpdateInput,
): Promise<SeoConfig> {
  const res = await fetch(`${API_BASE}/api/v1/admin/seo-config`, {
    method: "PUT",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!res.ok) throw await parseError(res, "SEO 설정 저장에 실패했습니다");
  return res.json() as Promise<SeoConfig>;
}

export async function uploadSeoAsset(
  kind: "favicon" | "og_image",
  file: File,
): Promise<SeoAssetUploadResult> {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(
    `${API_BASE}/api/v1/admin/seo-config/asset-upload?kind=${kind}`,
    {
      method: "POST",
      credentials: "include",
      body: formData,
    },
  );
  if (!res.ok) throw await parseError(res, "이미지 업로드에 실패했습니다");
  return res.json() as Promise<SeoAssetUploadResult>;
}

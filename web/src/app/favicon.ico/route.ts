import { readFile } from "node:fs/promises";
import path from "node:path";

// /favicon.ico 를 관리자 SEO 설정의 파비콘으로 "동적" 서빙하는 라우트 핸들러.
//
// 배경:
//   Next.js 에서 app/favicon.ico 는 빌드 시점에 고정되는 정적 파일이라,
//   관리자가 SEO 화면에서 파비콘을 바꿔도 검색엔진·브라우저가 기본으로 가져가는
//   표준 경로(/favicon.ico)에는 반영되지 않았다. (구버전 로고가 네이버 검색에 잔존)
//   Next 16 문서상 favicon 은 코드로 동적 생성할 수 없으므로(=icon 과 달리),
//   정적 favicon.ico 파일을 제거하고 이 라우트 핸들러가 그 경로를 대신 서빙한다.
//   → 매 요청마다 현재 설정된 파비콘 바이트를 가져와 그대로 돌려준다.
//
// 주의:
//   - public/ 자산(/favicon.png 등)은 HTTP 자기호출 대신 디스크에서 직접 읽는다.
//     (컨테이너 안 NEXT_PUBLIC_API_URL=localhost 자기호출 시 dev 서버가 교착됨)
//   - 모든 외부 fetch 에 타임아웃을 걸어 요청이 절대 멈추지 않게 한다.

export const runtime = "nodejs";

// 서버(SSR) 내부에서 백엔드를 호출할 때 쓰는 URL — 컨테이너 망에서는 http://api:8000.
const SERVER_API_BASE =
  process.env.API_INTERNAL_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://localhost:8000";

// 백엔드 미설정/장애 시 폴백할 번들 새 로고 (public/favicon.png).
const FALLBACK_PUBLIC_PATH = "/favicon.png";

// 외부 호출이 멈추지 않도록 하는 상한(ms).
const FETCH_TIMEOUT_MS = 2500;

interface Asset {
  buf: Uint8Array;
  contentType: string;
}

function contentTypeFor(p: string): string {
  if (p.endsWith(".svg")) return "image/svg+xml";
  if (p.endsWith(".ico")) return "image/x-icon";
  if (p.endsWith(".jpg") || p.endsWith(".jpeg")) return "image/jpeg";
  if (p.endsWith(".webp")) return "image/webp";
  return "image/png";
}

// public/ 디렉터리의 정적 자산을 디스크에서 직접 읽는다 (자기 HTTP 호출 회피).
async function readPublicFile(relPath: string): Promise<Asset | null> {
  const clean = relPath.split("?")[0].replace(/^\/+/, "");
  if (!clean || clean.includes("..")) return null;
  try {
    const abs = path.join(process.cwd(), "public", clean);
    const buf = await readFile(abs);
    return { buf, contentType: contentTypeFor(clean) };
  } catch {
    return null;
  }
}

// 외부(백엔드 /static 또는 CDN) 자산을 타임아웃과 함께 가져온다.
async function fetchBytes(url: string): Promise<Asset | null> {
  try {
    const r = await fetch(url, {
      signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
      next: { revalidate: 60 },
    });
    if (!r.ok) return null;
    const ab = await r.arrayBuffer();
    return {
      buf: new Uint8Array(ab),
      contentType: r.headers.get("content-type") ?? "image/png",
    };
  } catch {
    return null;
  }
}

async function resolveFaviconUrl(): Promise<string> {
  try {
    const r = await fetch(`${SERVER_API_BASE}/api/v1/admin/seo-config/public`, {
      signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
      next: { revalidate: 60 },
    });
    if (r.ok) {
      const body = (await r.json()) as { favicon_url?: string };
      const v = (body.favicon_url ?? "").trim();
      if (v) return v;
    }
  } catch {
    // 백엔드 미응답 — 폴백으로 진행.
  }
  return FALLBACK_PUBLIC_PATH;
}

export async function GET(): Promise<Response> {
  const faviconUrl = await resolveFaviconUrl();

  let asset: Asset | null = null;
  if (faviconUrl.startsWith("http://") || faviconUrl.startsWith("https://")) {
    asset = await fetchBytes(faviconUrl); // 외부 CDN
  } else if (faviconUrl.startsWith("/static/")) {
    asset = await fetchBytes(`${SERVER_API_BASE}${faviconUrl}`); // 업로드 자산(API)
  } else {
    asset = await readPublicFile(faviconUrl); // public/ 정적 자산
  }

  // 무엇이든 실패하면 번들 새 로고로 폴백.
  if (!asset) asset = await readPublicFile(FALLBACK_PUBLIC_PATH);
  if (!asset) return new Response(null, { status: 404 });

  return new Response(asset.buf, {
    headers: {
      "Content-Type": asset.contentType,
      // 검색엔진·브라우저 캐시 1시간 + 만료 후 24시간 동안 백그라운드 재검증.
      "Cache-Control": "public, max-age=3600, stale-while-revalidate=86400",
    },
  });
}

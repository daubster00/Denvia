import type { Metadata } from "next";
import "@wanteddev/wds/global.css";
import "../styles/globals.css";
import { Providers } from "./providers";
import { SkipLink } from "@/components/layout/SkipLink";
import { SupportWidget } from "@/features/support/components/SupportWidget";

// 서버 사이드에서 백엔드를 호출하기 위한 URL.
//  - 도커 컴포즈: API_INTERNAL_URL=http://api:8000 (compose 네트워크 내부 이름)
//  - 로컬 단일 프로세스: NEXT_PUBLIC_API_URL 폴백.
const SERVER_API_BASE =
  process.env.API_INTERNAL_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://localhost:8000";

// 브라우저가 실제로 favicon/og-image 를 요청할 때 사용하는 공개 URL.
const PUBLIC_API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// 백엔드 기본값과 일치 — fetch 실패 시 폴백.
const FALLBACK = {
  site_name: "Denvia — 치과 보험청구 AI 어시스턴트",
  site_description:
    "데스크 행정업무 및 치과 보험청구에 관한 정보를 제공하는 치과 전용 AI 챗봇입니다.",
  keywords: "",
  og_image_url: "/og-image.png",
  favicon_url: "/favicon.png",
};

interface SeoSnapshot {
  site_name: string;
  site_description: string;
  keywords: string;
  og_image_url: string;
  favicon_url: string;
}

function toPublicUrl(url: string): string {
  const v = (url ?? "").trim();
  if (!v) return "";
  if (v.startsWith("http://") || v.startsWith("https://")) return v;
  if (v.startsWith("/static/")) return `${PUBLIC_API_BASE}${v}`;
  return v; // /favicon.png 등 Next.js public/ 자산
}

async function loadSeo(): Promise<SeoSnapshot> {
  try {
    const res = await fetch(`${SERVER_API_BASE}/api/v1/admin/seo-config/public`, {
      next: { revalidate: 60 },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const body = (await res.json()) as SeoSnapshot;
    return body;
  } catch {
    return FALLBACK;
  }
}

export async function generateMetadata(): Promise<Metadata> {
  const seo = await loadSeo();
  const faviconUrl = toPublicUrl(seo.favicon_url) || FALLBACK.favicon_url;
  const ogImageUrl = toPublicUrl(seo.og_image_url) || FALLBACK.og_image_url;

  return {
    title: seo.site_name,
    description: seo.site_description,
    keywords: seo.keywords ? seo.keywords.split(",").map((s) => s.trim()).filter(Boolean) : undefined,
    icons: {
      icon: faviconUrl,
      apple: faviconUrl,
    },
    openGraph: {
      title: seo.site_name,
      description: seo.site_description,
      images: [{ url: ogImageUrl, width: 1200, height: 630, alt: seo.site_name }],
      type: "website",
    },
    twitter: {
      card: "summary_large_image",
      title: seo.site_name,
      description: seo.site_description,
      images: [ogImageUrl],
    },
  };
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko" data-theme="light" suppressHydrationWarning>
      {/* Pretendard Variable — CDN Dynamic Subset (font-display: swap) */}
      <head>
        <meta
          name="naver-site-verification"
          content="b4233b091f9c1e4e68d4e3c5debe9dd300d32ffa"
        />
        <link
          rel="stylesheet"
          as="style"
          href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css"
        />
      </head>
      <body>
        {/* Skip link — 포커스 시 표시, WCAG 2.4.1 (UX-DR24) */}
        <SkipLink />
        <Providers>
          <main id="main" tabIndex={-1}>
            {children}
          </main>
          {/* Story 4.5 — 우측 하단 고객 지원 위젯 (전 페이지, /admin/* 자동 가드) */}
          <SupportWidget />
        </Providers>
      </body>
    </html>
  );
}

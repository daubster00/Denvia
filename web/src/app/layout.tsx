import type { Metadata } from "next";
import "../styles/globals.css";
import { Providers } from "./providers";
import { SkipLink } from "@/components/layout/SkipLink";

export const metadata: Metadata = {
  title: "Denvia — 치과 임상 AI 어시스턴트",
  description: "치과 전문가를 위한 임상 Q&A 서비스. 최신 문헌을 기반으로 빠르고 신뢰할 수 있는 참고 답변을 제공합니다.",
  icons: {
    icon: "/favicon.png",
    apple: "/apple-icon.png",
  },
  openGraph: {
    title: "Denvia — 치과 임상 AI 어시스턴트",
    description: "치과 전문가를 위한 임상 Q&A 서비스. 최신 문헌을 기반으로 빠르고 신뢰할 수 있는 참고 답변을 제공합니다.",
    images: [{ url: "/og-image.png", width: 1200, height: 630, alt: "Denvia" }],
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "Denvia — 치과 임상 AI 어시스턴트",
    description: "치과 전문가를 위한 임상 Q&A 서비스.",
    images: ["/og-image.png"],
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko" data-theme="light">
      {/* Pretendard Variable — CDN Dynamic Subset (font-display: swap) */}
      <head>
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
        </Providers>
      </body>
    </html>
  );
}

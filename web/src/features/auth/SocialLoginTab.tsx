"use client";

import { useRef } from "react";

/** 소셜 로그인 탭 — 3사 버튼 UI. (Story 1.6 구현) */
export function SocialLoginTab({ mode = "login" }: { mode?: "login" | "signup" } = {}) {
  const navigatingRef = useRef(false);
  const handleSocialClick = (provider: "kakao" | "naver" | "google") => {
    if (navigatingRef.current) return;
    navigatingRef.current = true;
    const apiBase = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
    const params = new URLSearchParams({ mode });
    window.location.href = `${apiBase}/api/v1/auth/oauth/${provider}/authorize?${params}`;
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {/* 카카오 */}
      <button
        type="button"
        onClick={() => handleSocialClick("kakao")}
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          gap: 10,
          padding: "12px 0",
          backgroundColor: "#FEE500",
          border: "none",
          borderRadius: 8,
          fontSize: 15,
          fontWeight: 600,
          cursor: "pointer",
          color: "#000",
        }}
        aria-label="카카오로 로그인"
      >
        <span aria-hidden="true" style={{ fontSize: 18, lineHeight: 1 }}>💬</span>
        카카오로 계속하기
      </button>

      {/* 네이버 */}
      <button
        type="button"
        onClick={() => handleSocialClick("naver")}
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          gap: 10,
          padding: "12px 0",
          backgroundColor: "#03C75A",
          border: "none",
          borderRadius: 8,
          fontSize: 15,
          fontWeight: 600,
          cursor: "pointer",
          color: "#fff",
        }}
        aria-label="네이버로 로그인"
      >
        <span aria-hidden="true" style={{ fontWeight: 900, fontSize: 16, fontFamily: "sans-serif" }}>N</span>
        네이버로 계속하기
      </button>

      {/* 구글 */}
      <button
        type="button"
        onClick={() => handleSocialClick("google")}
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          gap: 10,
          padding: "12px 0",
          backgroundColor: "#fff",
          border: "1px solid #E1E2E4",
          borderRadius: 8,
          fontSize: 15,
          fontWeight: 600,
          cursor: "pointer",
          color: "#000",
        }}
        aria-label="구글로 로그인"
      >
        <GoogleColorIcon />
        구글로 계속하기
      </button>
    </div>
  );
}

function GoogleColorIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true" focusable="false">
      <path fill="#4285F4" d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.875 2.684-6.615z"/>
      <path fill="#34A853" d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 0 0 9 18z"/>
      <path fill="#FBBC05" d="M3.964 10.71A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.996 8.996 0 0 0 0 9c0 1.452.348 2.827.957 4.042l3.007-2.332z"/>
      <path fill="#EA4335" d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 0 0 .957 4.958L3.964 6.29C4.672 4.163 6.656 3.58 9 3.58z"/>
    </svg>
  );
}

"use client";

/**
 * Story 2.7 — 우측 하단 고객문의 Floating Action Button (FR32 부분 이행).
 *
 * 클릭 시 카카오톡 채널 새 탭으로 오픈. 인앱 폼/Drawer는 본 스토리 비범위 (Epic 4-5 본 구현).
 * NEXT_PUBLIC_KAKAO_CHANNEL_URL 미설정 시 위젯 자체 비렌더 → 빈 새 탭 열림 사고 방지.
 *
 * 보안: window.open에 noopener,noreferrer 필수 — reverse tabnabbing 방지 (NFR-S5).
 */
const KAKAO_URL = process.env.NEXT_PUBLIC_KAKAO_CHANNEL_URL;

export function CustomerInquiryFAB() {
  if (!KAKAO_URL) return null;

  return (
    <>
      <button
        type="button"
        aria-label="고객문의 — 카카오톡 채널 열기"
        onClick={() =>
          window.open(KAKAO_URL, "_blank", "noopener,noreferrer")
        }
        className="denvia-customer-fab"
        style={{
          position: "fixed",
          right: 24,
          bottom: 24,
          width: 56,
          height: 56,
          borderRadius: "50%",
          border: "none",
          background:
            "linear-gradient(135deg, #8B5CF6 0%, #D946EF 100%)",
          color: "#fff",
          fontSize: 24,
          cursor: "pointer",
          boxShadow: "0 4px 12px rgba(0, 0, 0, 0.15)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          zIndex: 90,
        }}
      >
        <span aria-hidden="true">💬</span>
      </button>
      <style>{`
        @media (max-width: 767px) {
          .denvia-customer-fab {
            right: 16px !important;
            bottom: 16px !important;
            width: 48px !important;
            height: 48px !important;
            font-size: 20px !important;
          }
        }
      `}</style>
    </>
  );
}

"use client";

import styles from "./CustomerInquiryFAB.module.css";

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
    <button
      type="button"
      aria-label="고객문의 — 카카오톡 채널 열기"
      onClick={() => window.open(KAKAO_URL, "_blank", "noopener,noreferrer")}
      className={styles.fab}
    >
      <span aria-hidden="true">💬</span>
    </button>
  );
}

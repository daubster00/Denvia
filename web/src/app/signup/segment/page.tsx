"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useSessionStore } from "@/stores/session-store";
import { SegmentSelect } from "@/features/auth/SegmentSelect";
import { setSegment } from "@/features/auth/api";

/**
 * /signup/segment — 가입유형·연차 설정 페이지 (AC-5, AC-6).
 * 비로그인 접근 시 로그인 팝업 열림.
 */
export default function SegmentPage() {
  const router = useRouter();
  const user = useSessionStore((s) => s.user);
  const openPopup = useSessionStore((s) => s.openPopup);

  // 비로그인 보호
  useEffect(() => {
    if (user === null) {
      openPopup("email");
      router.replace("/");
    }
  }, [user, openPopup, router]);

  // 이미 세그먼트 설정된 경우 메인으로
  useEffect(() => {
    if (user?.segment) {
      router.replace("/");
    }
  }, [user, router]);

  const handleComplete = async (
    segment: "doctor" | "hygienist" | "student_other",
    years_of_experience?: number
  ) => {
    await setSegment({ segment, years_of_experience });
    router.push("/");
  };

  if (!user || user.segment) return null;

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: "24px 16px",
        background: "#FAFAFA",
      }}
    >
      <div
        style={{
          width: "min(420px, 100%)",
          background: "#fff",
          borderRadius: 16,
          boxShadow: "0 4px 24px rgba(0,0,0,0.10)",
          padding: "32px 28px",
        }}
      >
        <h1 style={{ fontSize: 22, fontWeight: 700, margin: "0 0 8px" }}>
          가입유형 설정
        </h1>
        <p style={{ fontSize: 14, color: "#70737C", marginBottom: 24 }}>
          한 번 설정하면 변경은 고객 문의로 요청해주세요.
        </p>

        <SegmentSelect onComplete={handleComplete} />
      </div>
    </div>
  );
}

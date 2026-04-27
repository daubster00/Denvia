"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Typography } from "@wanteddev/wds";
import { useSessionStore } from "@/stores/session-store";
import { SegmentSelect } from "@/features/auth/SegmentSelect";
import { fetchMe, setSegment } from "@/features/auth/api";
import styles from "../signup-shell.module.css";

/**
 * /signup/segment — 가입유형·연차 설정 페이지 (AC-5, AC-6).
 * 비로그인 접근 시 로그인 팝업 열림.
 *
 * 세션 쿼리가 pending 중일 때는 판단을 보류한다 — OAuth AC-4 경로에서
 * 백엔드가 직접 302로 이 페이지에 도달시키면 session-store의 user는
 * 초기값 null 이므로, pending 상태 확인 없이 바로 리다이렉트하면 튕긴다.
 */
export default function SegmentPage() {
  const router = useRouter();
  const openPopup = useSessionStore((s) => s.openPopup);

  // SessionBootstrap과 동일한 queryKey — 캐시 공유 + pending 상태 감지
  const { data: user, isPending } = useQuery({
    queryKey: ["session"],
    queryFn: fetchMe,
    retry: 1,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });

  useEffect(() => {
    if (isPending) return; // 쿼리 응답 대기 중 — 판단 보류

    if (!user) {
      openPopup("email");
      router.replace("/");
      return;
    }

    if (user.segment) {
      router.replace("/");
    }
  }, [isPending, user, openPopup, router]);

  const handleComplete = async (
    segment: "doctor" | "hygienist" | "student_other",
    years_of_experience?: number
  ) => {
    await setSegment({ segment, years_of_experience });
    router.push("/");
  };

  if (isPending || !user || user.segment) return null;

  return (
    <div className={styles.shell}>
      <div className={styles.cardSegment}>
        <div className={styles.headerStackSegment}>
          <Typography
            as="h1"
            variant="heading1"
            weight="bold"
            color="semantic.label.normal"
          >
            가입유형 설정
          </Typography>
          <Typography
            as="p"
            variant="body2-reading"
            color="semantic.label.alternative"
          >
            한 번 설정하면 변경은 고객 문의로 요청해주세요.
          </Typography>
        </div>

        <SegmentSelect onComplete={handleComplete} />
      </div>
    </div>
  );
}

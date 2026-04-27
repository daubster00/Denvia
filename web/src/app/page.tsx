"use client";

import { useQuery } from "@tanstack/react-query";
import { TopNav } from "@/components/layout/TopNav";
import { AdvisoryChip } from "@/components/brand/AdvisoryChip";
import { ChatInput } from "@/features/qa/ChatInput";
import { useSessionStore } from "@/stores/session-store";
import { fetchMe } from "@/features/auth/api";
import {
  AuthenticatedQAExperience,
  HeroCopy,
  HeroSection,
} from "@/app/_components/QAHomeExperience";
import styles from "@/app/_components/QAHomeExperience.module.css";

/**
 * F-000 메인 랜딩.
 *
 * 비로그인: 히어로 카피 + readonly ChatInput → 클릭 시 로그인 팝업 (F-001).
 * 로그인: 히어로 카피 + 활성 ChatInput — 입력 후 제출 시 /chat 으로 이동.
 *
 * /(메인)은 항상 hero — 실제 대화(ChatShell) 렌더링은 /chat 에서만 수행한다
 * (qa-store 메시지 존재 여부와 무관). 새 질문 제출 시 replaceMessages 가
 * 이전 메시지를 덮어쓰면서 /chat 으로 push 한다.
 *
 * 인증은 두 출처를 모두 인정한다:
 *   - useSessionStore.user: 팝업 로그인(EmailLoginTab → setUser)이 query invalidate 없이 채운 값
 *   - useQuery(["session"]).data: 직접 / 진입 시 SessionBootstrap이 띄운 동일 query 캐시
 */
export default function Home() {
  const user = useSessionStore((s) => s.user);
  const { data, isLoading, isError } = useQuery({
    queryKey: ["session"],
    queryFn: fetchMe,
    retry: 1,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });
  const isAuthenticated = !!user || (!!data && !isError);

  if (isAuthenticated) {
    return <AuthenticatedQAExperience />;
  }
  return <UnauthenticatedHome isLoading={isLoading} />;
}

function UnauthenticatedHome({ isLoading }: { isLoading: boolean }) {
  return (
    <>
      <TopNav />
      <HeroSection>
        <HeroCopy />
        {isLoading ? (
          <div aria-hidden="true" className={styles.heroPlaceholder} />
        ) : (
          <ChatInput variant="hero" />
        )}
        <AdvisoryChip />
      </HeroSection>
    </>
  );
}

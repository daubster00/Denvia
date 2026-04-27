"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/**
 * /chat 은 더 이상 별도 라우트가 아니다.
 * 통합 홈(/)이 인증 상태에 따라 hero ↔ chat shell 을 직접 전환한다.
 * 직접 진입 또는 북마크 호환성을 위해 / 로 redirect 한다.
 */
export default function ChatPage() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/");
  }, [router]);
  return null;
}

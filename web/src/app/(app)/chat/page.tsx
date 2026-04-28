"use client";

import { AuthenticatedQAExperience } from "@/app/_components/QAHomeExperience";

/**
 * /chat 직접 진입용 Q&A 화면.
 * 통합 홈(/)과 같은 인증 후 채팅 경험을 렌더하되 URL은 /chat에 유지한다.
 */
export default function ChatPage() {
  return <AuthenticatedQAExperience />;
}

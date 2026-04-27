"use client";

import { useState, useRef } from "react";
import { TopNav } from "@/components/layout/TopNav";
import { ChatShell } from "@/features/qa/components/ChatShell";
import { CustomerInquiryFAB } from "@/components/feedback/CustomerInquiryFAB";
import { useQAStore } from "@/stores/qa-store";
import { useQAStream } from "@/features/qa/hooks/useQAStream";
import { useQuota } from "@/features/qa/hooks/useQuota";

export default function ChatPage() {
  const [inputValue, setInputValue] = useState("");
  const [showDelayBanner, setShowDelayBanner] = useState(false);
  const messages = useQAStore((s) => s.messages);
  const stream = useQAStream();
  const lastUserTextRef = useRef<string>("");
  const { data: quotaData } = useQuota();

  async function handleSubmit(text: string) {
    lastUserTextRef.current = text;
    setInputValue("");
    // AC-9: submit 직후 FreeDelayBanner 트리거
    setShowDelayBanner(true);
    await stream.submit(text);
  }

  const isStreaming = messages.some(
    (m) => m.role === "assistant" && m.status === "pending"
  );

  return (
    <>
      <TopNav />
      <ChatShell
        inputValue={inputValue}
        onInputChange={setInputValue}
        onSubmit={handleSubmit}
        isStreaming={isStreaming}
        onRetry={() => stream.submit(lastUserTextRef.current)}
        quotaData={quotaData}
        showDelayBanner={showDelayBanner}
      />
      <CustomerInquiryFAB />
    </>
  );
}

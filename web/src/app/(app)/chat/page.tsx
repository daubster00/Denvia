"use client";

import { useState, useRef } from "react";
import { TopNav } from "@/components/layout/TopNav";
import { ChatShell } from "@/features/qa/components/ChatShell";
import { CustomerInquiryFAB } from "@/components/feedback/CustomerInquiryFAB";
import { useQAStore } from "@/stores/qa-store";
import { useQAStream } from "@/features/qa/hooks/useQAStream";

export default function ChatPage() {
  const [inputValue, setInputValue] = useState("");
  const messages = useQAStore((s) => s.messages);
  const stream = useQAStream();
  const lastUserTextRef = useRef<string>("");

  async function handleSubmit(text: string) {
    lastUserTextRef.current = text;
    setInputValue("");
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
      />
      <CustomerInquiryFAB />
    </>
  );
}

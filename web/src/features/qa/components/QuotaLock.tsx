"use client";

import { useRouter } from "next/navigation";
import { useQuotaStore } from "@/stores/quota-store";

export function QuotaLock() {
  const { locked, payload, dismiss } = useQuotaStore();
  const router = useRouter();

  if (!locked || !payload) return null;

  const isInternal = payload.reason === "QUOTA_EXCEEDED_INTERNAL_SAFETY_LIMIT";
  const headline = isInternal
    ? "일시적 시스템 보호 제한에 도달했습니다."
    : `오늘의 ${payload.dailyLimit}회를 모두 사용했어요.`;
  const body = isInternal
    ? "고객문의로 연락주세요."
    : "내일 다시 오시거나, Pro로 계속 진료에 활용해보세요.";

  return (
    <div
      role="alert"
      style={{
        border: "1.5px dashed #C7C7CC",
        backgroundColor: "#FAFAFA",
        padding: "16px 20px",
        borderRadius: 12,
        margin: "12px 0",
        display: "flex",
        flexDirection: "column",
        gap: 12,
        maxWidth: 640,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span aria-hidden="true">잠금</span>
        <strong style={{ fontSize: 14 }}>{headline}</strong>
      </div>
      <p style={{ margin: 0, fontSize: 13, color: "#5A5C63" }}>{body}</p>
      <div style={{ display: "flex", gap: 8 }}>
        {!isInternal && (
          <button
            type="button"
            onClick={dismiss}
            style={{
              padding: "8px 16px",
              fontSize: 13,
              border: "1px solid #E1E2E4",
              borderRadius: 8,
              background: "transparent",
              color: "#5A5C63",
              cursor: "pointer",
            }}
          >
            내일 다시
          </button>
        )}
        {!isInternal && payload.showUpgradePrompt && payload.showSubscribeButton && (
          <button
            type="button"
            onClick={() => router.push("/subscribe")}
            style={{
              padding: "8px 16px",
              fontSize: 13,
              border: "none",
              borderRadius: 8,
              background: "linear-gradient(135deg, #8B5CF6 0%, #D946EF 100%)",
              color: "#fff",
              cursor: "pointer",
            }}
          >
            Pro로 계속
          </button>
        )}
      </div>
    </div>
  );
}

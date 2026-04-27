"use client";

import { useSessionStore } from "@/stores/session-store";
import { LogoLink } from "@/components/brand/LogoLink";

export function AdminTopNav() {
  const user = useSessionStore((s) => s.user);

  return (
    <header
      style={{
        height: "var(--topnav-height, 64px)",
        borderBottom: "1px solid #E1E2E4",
        backgroundColor: "#fff",
        display: "flex",
        alignItems: "center",
        padding: "0 24px",
        justifyContent: "space-between",
        flexShrink: 0,
      }}
    >
      <LogoLink />

      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        {user && (
          <span
            style={{
              fontSize: 13,
              color: "#6B7280",
            }}
          >
            {user.email}
          </span>
        )}
        <span
          style={{
            fontSize: 12,
            fontWeight: 600,
            padding: "2px 8px",
            borderRadius: 4,
            backgroundColor: "#EDE9FE",
            color: "#7C3AED",
          }}
        >
          관리자
        </span>
      </div>
    </header>
  );
}

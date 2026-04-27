"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { fetchMe } from "@/features/auth/api";
import { AdminSidebar } from "@/components/layout/AdminSidebar";
import { AdminTopNav } from "@/components/layout/AdminTopNav";

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const { data: session, isLoading } = useQuery({
    queryKey: ["session"],
    queryFn: fetchMe,
  });

  useEffect(() => {
    if (!isLoading && (!session || session.role !== "admin")) {
      // 토스트 없이 조용히 — 관리자 경로 존재 사실 비노출 (AC-3)
      router.replace("/");
    }
  }, [session, isLoading, router]);

  if (isLoading || !session || session.role !== "admin") {
    return null;
  }

  return (
    <div style={{ display: "flex", height: "100vh", overflow: "hidden" }}>
      <AdminSidebar />
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          flex: 1,
          overflow: "hidden",
        }}
      >
        <AdminTopNav />
        {/* 모바일 경고 — 숨기는 대신 안내 (UX-DR23) */}
        <div
          style={{
            display: "none",
            padding: "8px 16px",
            backgroundColor: "#FEF3C7",
            borderBottom: "1px solid #FDE68A",
          }}
          className="mobile-admin-warning"
        >
          <p style={{ fontSize: 13, color: "#92400E", margin: 0 }}>
            데스크톱에서 최적 사용 가능합니다.
          </p>
        </div>
        <main
          id="admin-main"
          tabIndex={-1}
          style={{ flex: 1, overflow: "auto" }}
        >
          {children}
        </main>
      </div>
      <style>{`
        @media (max-width: 767px) {
          .mobile-admin-warning { display: block !important; }
        }
      `}</style>
    </div>
  );
}

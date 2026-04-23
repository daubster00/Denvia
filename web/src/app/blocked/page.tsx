import { TopNav } from "@/components/layout/TopNav";

/**
 * 차단 사용자 페이지 — FR45.
 * 구체 사유 비공개: "이용이 제한되었습니다" 카피만 표시.
 */
export default function BlockedPage() {
  return (
    <>
      <TopNav />
      <main
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          minHeight: "calc(100vh - 64px)",
          padding: "40px 16px",
          textAlign: "center",
        }}
      >
        <div style={{ display: "flex", flexDirection: "column", gap: 16, maxWidth: 400 }}>
          <span style={{ fontSize: 48 }} role="img" aria-label="이용 제한">🚫</span>
          <h1 style={{ margin: 0, fontSize: 24, fontWeight: 700, color: "#171719" }}>
            이용이 제한되었습니다
          </h1>
          <p style={{ margin: 0, fontSize: 15, color: "#70737C", lineHeight: 1.6 }}>
            현재 계정의 서비스 이용이 제한되어 있습니다.
            <br />
            문의 사항이 있으시면 고객센터로 연락해주세요.
          </p>
        </div>
      </main>
    </>
  );
}

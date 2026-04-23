import { TopNav } from "@/components/layout/TopNav";
import { ChatInput } from "@/features/qa/ChatInput";
import { AdvisoryChip } from "@/components/brand/AdvisoryChip";

/**
 * F-000 메인 랜딩 — 비로그인 뷰.
 * ChatInput은 비활성화, 클릭/포커스 시 로그인 팝업 트리거.
 */
export default function Home() {
  return (
    <>
      <TopNav />

      {/* 히어로 섹션 */}
      <section
        aria-label="서비스 소개"
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          minHeight: "calc(100vh - 64px)",
          padding: "40px 16px 80px",
        }}
      >
        <div
          style={{
            width: "100%",
            maxWidth: 720,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 32,
            textAlign: "center",
          }}
        >
          {/* 서비스 소개 카피 — width:100% 로 shrink-wrap 방지, 이후 textAlign:center 유효 */}
          <div style={{ display: "flex", flexDirection: "column", gap: 12, width: "100%" }}>
            <h1
              style={{
                margin: 0,
                fontSize: "clamp(26px, 4vw, 40px)",
                fontWeight: 700,
                color: "#171719",
                lineHeight: 1.25,
                letterSpacing: "-0.5px",
                textAlign: "center",
              }}
            >
              치과 임상 질문,{" "}
              <span style={{ background: "linear-gradient(135deg, #8B5CF6 0%, #D946EF 100%)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
                AI가 참고 답변을 드립니다
              </span>
            </h1>
            <p
              style={{
                margin: "0 auto",
                fontSize: 16,
                color: "#70737C",
                lineHeight: 1.6,
                maxWidth: 480,
                textAlign: "center",
              }}
            >
              치과 전문가를 위한 임상 Q&A 서비스. 최신 문헌을 기반으로 빠르고 신뢰할 수 있는 참고 답변을 제공합니다.
            </p>
          </div>

          {/* 히어로 ChatInput — 비활성 (로그인 후 이용 가능) */}
          <ChatInput variant="hero" />

          {/* 면책 고지 — 상시 표시 (NFR-C6) */}
          <AdvisoryChip />
        </div>
      </section>

      <style>{`
        @media (max-width: 767px) {
          section[aria-label="서비스 소개"] {
            min-height: calc(100vh - 56px) !important;
          }
        }
        @media (min-width: 1280px) {
          section[aria-label="서비스 소개"] > div {
            max-width: 720px !important;
          }
        }
      `}</style>
    </>
  );
}

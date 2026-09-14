/**
 * 지출 내역(챗봇 대화 / 지식 재구축) 공통 문구 — 수정요청 게시판 #145.
 *
 * 배경: 관리자 화면의 지출은 그동안 챗봇 대화 비용만 합산했다. 지식 문서를 다시
 * 읽혀 검색 색인을 새로 만드는 "지식 재구축" 작업도 OpenAI 에 돈이 나가는데
 * 기록이 남지 않아, 화면 금액과 실제 청구액이 달랐다. 이제 두 항목을 모두
 * 합산하고, 화면에서는 나눠서 보여준다.
 */

/** 지식 재구축 비용 기록이 시작된 날 (이 날 이전 재구축분은 금액을 알 수 없음). */
export const REBUILD_COST_TRACKING_SINCE = "2026-09-14";

/** 합계가 왜 늘었는지 / 과거분이 왜 빠져 있는지 설명하는 안내 문구. */
export const REBUILD_COST_NOTICE =
  `지출에는 챗봇 대화 비용과 지식 재구축 비용이 함께 들어갑니다. ` +
  `${REBUILD_COST_TRACKING_SINCE} 이전에 실행한 재구축은 비용이 기록되지 않아 합계에서 빠져 있습니다.`;

/** "챗봇 대화 ₩○○ + 지식 재구축 ₩○○" 한 줄 요약. */
export function formatCostBreakdown(
  chatKrw: number,
  rebuildKrw: number,
): string {
  const won = (v: number) => `₩${Math.round(v).toLocaleString("ko-KR")}`;
  return `챗봇 대화 ${won(chatKrw)} + 지식 재구축 ${won(rebuildKrw)}`;
}

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { QALogDetailDrawer } from "../QALogDetailDrawer";
import type { UserQALogDetail } from "@/features/admin-users/api/activity";
import * as activityApi from "@/features/admin-users/api/activity";

const baseDetail: UserQALogDetail = {
  qa_log_id: 170,
  question_text: "임플란트 보험 청구 코드는?",
  normalized_query: "임플란트 수가",
  retrieved_docs: [],
  prompt_text: null,
  answer_text: "U2240 코드로 청구합니다.",
  rule_matched: false,
  status: "completed",
  input_tokens: 12,
  output_tokens: 34,
  cost_usd: "0.002485",
  cost_krw: 4,
  usd_to_krw: 1505,
  usd_to_krw_updated_at: "2026-07-16T08:00:20.446552+00:00",
  usd_to_krw_search_date: "2026-07-14",
  latency_ms: 1234,
  created_at: "2026-07-16T10:23:00+09:00",
};

function renderWithClient(ui: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("QALogDetailDrawer — 원화(KRW) 비용 표기 (#134)", () => {
  it("cost_usd 가 있으면 '비용(원화 환산)' 행을 formatKRW 로 렌더", async () => {
    vi.spyOn(activityApi, "fetchUserQALogDetail").mockResolvedValue(baseDetail);
    renderWithClient(
      <QALogDetailDrawer userId={70} qaLogId={170} onClose={vi.fn()} />
    );
    await waitFor(() => {
      expect(screen.getByText("비용(원화 환산)")).toBeTruthy();
    });
    // 4원 → "₩4"
    expect(screen.getByText("₩4")).toBeTruthy();
    // USD 원본도 여전히 노출
    expect(screen.getByText("0.002485")).toBeTruthy();
  });

  it("환율 근거 문구를 표시 (기준 환율 + 영업일 + 갱신 시각)", async () => {
    vi.spyOn(activityApi, "fetchUserQALogDetail").mockResolvedValue(baseDetail);
    renderWithClient(
      <QALogDetailDrawer userId={70} qaLogId={170} onClose={vi.fn()} />
    );
    await waitFor(() => {
      expect(
        screen.getByText(/환율 기준: 1 USD = ₩1,505/)
      ).toBeTruthy();
    });
    expect(screen.getByText(/2026-07-14 환율/)).toBeTruthy();
  });

  it("cost_usd 가 null 이면 원화 행은 '—' (historical 행)", async () => {
    vi.spyOn(activityApi, "fetchUserQALogDetail").mockResolvedValue({
      ...baseDetail,
      cost_usd: null,
      cost_krw: null,
    });
    renderWithClient(
      <QALogDetailDrawer userId={70} qaLogId={167} onClose={vi.fn()} />
    );
    await waitFor(() => {
      expect(screen.getByText("비용(원화 환산)")).toBeTruthy();
    });
    // USD·KRW 모두 "—"; 환율 근거 문구는 숨김.
    expect(screen.queryByText(/환율 기준/)).toBeNull();
  });
});

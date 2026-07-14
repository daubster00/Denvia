import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AnswerDetailDrawer } from "../AnswerDetailDrawer";
import type {
  FeedbackDetail,
  FeedbackItem,
} from "../../api/analytics";
import * as analyticsApi from "../../api/analytics";

vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

const sampleItem: FeedbackItem = {
  qa_log_id: 1001,
  question_text: "임플란트 보철물 선택 기준은 무엇인가요?",
  answer_text: "임플란트 보철물은 크라운·브릿지·틀니 세 종류입니다.",
  rating: "good",
  segment: "doctor",
  user_id: 42,
  email: "doctor@denvia.test",
  created_at: "2026-04-15T10:23:00+09:00",
  reviewed_at: null,
};

const sampleDetail: FeedbackDetail = {
  qa_log_id: 1001,
  question_text: sampleItem.question_text,
  normalized_query: "임플란트 보철물 종류",
  retrieved_docs: [
    {
      page_content: "크라운은 단일 치아 보철물입니다.",
      metadata: { source: "doc-a.pdf", page: 12 },
    },
    {
      page_content: "브릿지는 결손 치아를 인접 치아로 지지합니다.",
      metadata: { source: "doc-b.pdf" },
    },
  ],
  prompt_text:
    "당신은 치과 행정 어시스턴트입니다.\n\n질문: <샘플 질문>\n\n문서:\n<샘플 문서 본문 1>\n<샘플 문서 본문 2>\n\n답변:",
  answer_text: sampleItem.answer_text,
  rule_matched: false,
  status: "ok",
  input_tokens: null,
  output_tokens: null,
  cost_usd: null,
  cost_krw: null,
  usd_to_krw: 1400,
  usd_to_krw_updated_at: null,
  usd_to_krw_search_date: null,
  latency_ms: null,
  created_at: sampleItem.created_at,
};

function renderWithClient(ui: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(analyticsApi, "fetchFeedbackDetail").mockResolvedValue(sampleDetail);
});

describe("AnswerDetailDrawer", () => {
  it("item=null 이면 렌더하지 않음", () => {
    const { container } = renderWithClient(
      <AnswerDetailDrawer item={null} onClose={vi.fn()} />
    );
    expect(container.firstChild).toBeNull();
  });

  it("질문/답변 전문 렌더", () => {
    renderWithClient(<AnswerDetailDrawer item={sampleItem} onClose={vi.fn()} />);
    expect(screen.getByText(sampleItem.question_text)).toBeTruthy();
    expect(screen.getByText(sampleItem.answer_text!)).toBeTruthy();
  });

  it("aria-modal=true + role=dialog + aria-label", () => {
    renderWithClient(<AnswerDetailDrawer item={sampleItem} onClose={vi.fn()} />);
    const dialog = screen.getByRole("dialog");
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    expect(dialog.getAttribute("aria-label")).toBe("답변 상세");
  });

  it("닫기 버튼 클릭 → onClose 호출", () => {
    const onClose = vi.fn();
    renderWithClient(<AnswerDetailDrawer item={sampleItem} onClose={onClose} />);
    const closeBtn = screen.getByRole("button", { name: "상세 패널 닫기" });
    fireEvent.click(closeBtn);
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("ESC 키 → onClose 호출", () => {
    const onClose = vi.fn();
    renderWithClient(<AnswerDetailDrawer item={sampleItem} onClose={onClose} />);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("backdrop 클릭 → onClose 호출", () => {
    const onClose = vi.fn();
    renderWithClient(
      <AnswerDetailDrawer item={sampleItem} onClose={onClose} />
    );
    // 딤 배경(=dialog 컨테이너) 자체를 클릭하면 닫힌다.
    const backdrop = screen.getByRole("dialog");
    fireEvent.click(backdrop);
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("good rating — 👍 GOOD 텍스트 렌더", () => {
    renderWithClient(<AnswerDetailDrawer item={sampleItem} onClose={vi.fn()} />);
    expect(screen.getByText("👍 GOOD")).toBeTruthy();
  });

  it("bad rating — 👎 BAD 텍스트 렌더", () => {
    const badItem = { ...sampleItem, rating: "bad" as const };
    renderWithClient(<AnswerDetailDrawer item={badItem} onClose={vi.fn()} />);
    expect(screen.getByText("👎 BAD")).toBeTruthy();
  });

  it("계정 이메일을 고객 관리 페이지 링크로 노출", () => {
    renderWithClient(<AnswerDetailDrawer item={sampleItem} onClose={vi.fn()} />);
    const link = screen.getByRole("link", { name: /doctor@denvia\.test/ });
    expect(link.getAttribute("href")).toBe("/admin/users/42");
  });

  it("탈퇴회원(user_id=null)이면 링크 대신 '탈퇴회원' 표시", () => {
    const anon: FeedbackItem = { ...sampleItem, user_id: null, email: null };
    renderWithClient(<AnswerDetailDrawer item={anon} onClose={vi.fn()} />);
    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.getByText("탈퇴회원")).toBeTruthy();
  });

  it("top-k 검색 문서가 로드되면 건수와 본문 렌더", async () => {
    renderWithClient(<AnswerDetailDrawer item={sampleItem} onClose={vi.fn()} />);
    await waitFor(() => {
      expect(screen.getByText(/top-k 검색에 들어온 문서 \(2건\)/)).toBeTruthy();
    });
    expect(screen.getByText(/크라운은 단일 치아 보철물입니다/)).toBeTruthy();
    expect(screen.getByText(/브릿지는 결손 치아를 인접 치아로 지지합니다/)).toBeTruthy();
    expect(screen.getByText("#1")).toBeTruthy();
    expect(screen.getByText("#2")).toBeTruthy();
  });

  it("문서 metadata가 pill로 노출", async () => {
    renderWithClient(<AnswerDetailDrawer item={sampleItem} onClose={vi.fn()} />);
    await waitFor(() => {
      expect(screen.getByText(/doc-a\.pdf/)).toBeTruthy();
    });
    // 두 문서 모두 source 키를 가짐 → 2개
    expect(screen.getAllByText("source:").length).toBe(2);
    expect(screen.getByText("page:")).toBeTruthy();
  });

  it("rule_matched=true 면 검색 문서 없음 안내", async () => {
    vi.spyOn(analyticsApi, "fetchFeedbackDetail").mockResolvedValue({
      ...sampleDetail,
      rule_matched: true,
      retrieved_docs: [],
    });
    renderWithClient(<AnswerDetailDrawer item={sampleItem} onClose={vi.fn()} />);
    await waitFor(() => {
      expect(
        screen.getByText(/룰 매칭 경로로 응답된 질의입니다\. retriever를 거치지 않으므로/)
      ).toBeTruthy();
    });
  });

  it("retrieved_docs=[]면 빈 상태 메시지 표시", async () => {
    vi.spyOn(analyticsApi, "fetchFeedbackDetail").mockResolvedValue({
      ...sampleDetail,
      retrieved_docs: [],
    });
    renderWithClient(<AnswerDetailDrawer item={sampleItem} onClose={vi.fn()} />);
    await waitFor(() => {
      expect(
        screen.getByText(/검색 문서 기록이 없습니다/)
      ).toBeTruthy();
    });
  });

  it("fetch 에러 시 에러 메시지 표시", async () => {
    vi.spyOn(analyticsApi, "fetchFeedbackDetail").mockRejectedValue(
      new Error("boom")
    );
    renderWithClient(<AnswerDetailDrawer item={sampleItem} onClose={vi.fn()} />);
    await waitFor(() => {
      expect(
        screen.getByText("상세 정보를 불러오지 못했습니다.")
      ).toBeTruthy();
    });
  });
});

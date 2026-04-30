import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ComingSoonWidget } from "../ComingSoonWidget";

describe("ComingSoonWidget", () => {
  it("준비 중 배지 + 설명 + 스토리 ref 표시", () => {
    render(
      <ComingSoonWidget
        title="가입자 추이"
        description="가입/탈퇴 추이를 30일 누적으로 확인합니다."
        storyRef="Story 5.3에서 가입/탈퇴 추이 API 연결 예정"
      />,
    );
    expect(screen.getByText("준비 중")).toBeTruthy();
    expect(screen.getByText("가입자 추이")).toBeTruthy();
    expect(screen.getByText(/30일 누적/)).toBeTruthy();
    expect(
      screen.getByText("Story 5.3에서 가입/탈퇴 추이 API 연결 예정"),
    ).toBeTruthy();
  });

  it("숫자/통계 미렌더 — 본문에 0~9 자체가 storyRef 외에 등장하지 않음", () => {
    render(
      <ComingSoonWidget
        title="피드백 비율"
        description="GOOD/BAD 응답 비율을 확인합니다."
        storyRef="Story 5.4에서 GOOD/BAD 분석 연결 예정"
      />,
    );
    // 차트 placeholder 자리는 텍스트로 채워져 있어야 함 (mock 숫자 없음)
    expect(screen.getByLabelText(/피드백 비율 차트 자리 \(준비 중\)/)).toBeTruthy();
  });

  it("placeholderHint override", () => {
    render(
      <ComingSoonWidget
        title="재무 요약"
        description="매출과 토큰 비용 차액을 표시합니다."
        storyRef="HOLD-PG 해제 후 매출/토큰 비용 차액 연결"
        placeholderHint="결제 데이터가 들어오면 차트가 표시됩니다."
      />,
    );
    expect(
      screen.getByText("결제 데이터가 들어오면 차트가 표시됩니다."),
    ).toBeTruthy();
  });

  it("detailDisabledTitle 미지정 시 storyRef를 disabled title로 사용", () => {
    render(
      <ComingSoonWidget
        title="구독 현황"
        description="무료/Pro 비율과 갱신 예정일 표시"
        storyRef="HOLD-PG 이후 연결"
      />,
    );
    const disabled = screen.getByText("상세 준비 중");
    expect(disabled.getAttribute("title")).toBe("HOLD-PG 이후 연결");
  });
});

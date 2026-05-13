import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { SegmentCard } from "../SegmentCard";

describe("SegmentCard — Story 4.3 AC-5", () => {
  it("doctor + 7년차 → 라벨 + 연차 노출, 편집 UI 미노출", () => {
    render(<SegmentCard segment="doctor" yearsOfExperience={7} />);
    expect(screen.getByText("치과의사")).toBeDefined();
    expect(screen.getByText("7년차")).toBeDefined();
    expect(screen.queryByRole("button", { name: /편집|수정/ })).toBeNull();
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(screen.queryByRole("combobox")).toBeNull();
  });

  it("hygienist + 3년차 라벨", () => {
    render(<SegmentCard segment="hygienist" yearsOfExperience={3} />);
    expect(screen.getByText("치과위생사")).toBeDefined();
    expect(screen.getByText("3년차")).toBeDefined();
  });

  it("student_other → '학생·기타' 라벨, 연차 카드 미노출", () => {
    render(<SegmentCard segment="student_other" yearsOfExperience={null} />);
    expect(screen.getByText("학생·기타")).toBeDefined();
    expect(screen.queryByText(/년차/)).toBeNull();
  });

  it("segment === null → 회원 정보 완성 안내 + /signup/segment 링크", () => {
    render(<SegmentCard segment={null} yearsOfExperience={null} />);
    expect(screen.getByText("회원 정보를 완성해주세요.")).toBeDefined();
    const link = screen.getByRole("link", { name: "가입유형 설정하기" });
    expect(link.getAttribute("href")).toBe("/signup/segment");
  });

  it("문의하기 안내 카피 + 이메일 주소 0건 (project_email_zero_policy)", () => {
    const { container } = render(
      <SegmentCard segment="doctor" yearsOfExperience={5} />
    );
    expect(
      screen.getByText(/변경은 우측 하단 문의하기를 통해 요청해주세요/)
    ).toBeDefined();
    // mailto: 미사용 + 이메일 주소 패턴 미노출
    expect(container.innerHTML.includes("mailto:")).toBe(false);
    expect(/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/.test(container.textContent ?? "")).toBe(
      false
    );
  });
});

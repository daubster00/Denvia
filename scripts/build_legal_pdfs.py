"""Denvia 이용약관 / 개인정보처리방침 PDF 빌더.

입력: docs/legal/terms.md, docs/legal/privacy.md
출력:
    자료/Denvia_이용약관_v0.3_2026-06-05.pdf
    자료/Denvia_개인정보처리방침_v0.2_2026-06-05.pdf

reportlab(Platypus)로 한글 PDF를 직접 생성한다. Malgun Gothic(맑은 고딕)을 등록해 사용.

실행:
    py -3 scripts/build_legal_pdfs.py
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs" / "legal"
OUT_DIR = ROOT / "자료"


# ──────────────────────────────────────────────────────────────────────────────
# 폰트 등록
# ──────────────────────────────────────────────────────────────────────────────

FONT_REG = "Malgun"
FONT_BOLD = "MalgunBold"

pdfmetrics.registerFont(TTFont(FONT_REG, "C:/Windows/Fonts/malgun.ttf"))
pdfmetrics.registerFont(TTFont(FONT_BOLD, "C:/Windows/Fonts/malgunbd.ttf"))
pdfmetrics.registerFontFamily(
    FONT_REG, normal=FONT_REG, bold=FONT_BOLD, italic=FONT_REG, boldItalic=FONT_BOLD
)


# ──────────────────────────────────────────────────────────────────────────────
# 스타일
# ──────────────────────────────────────────────────────────────────────────────

COLOR_TEXT = colors.HexColor("#1f2933")
COLOR_MUTED = colors.HexColor("#52606d")
COLOR_BRAND = colors.HexColor("#0f4c81")
COLOR_RULE = colors.HexColor("#cbd2d9")
COLOR_TABLE_HEAD_BG = colors.HexColor("#f1f5f9")
COLOR_TABLE_BORDER = colors.HexColor("#cbd2d9")
COLOR_QUOTE_BG = colors.HexColor("#f5f7fa")
COLOR_QUOTE_BAR = colors.HexColor("#0f4c81")


def make_styles() -> dict[str, ParagraphStyle]:
    base = ParagraphStyle(
        "base",
        fontName=FONT_REG,
        fontSize=10.5,
        leading=16,
        textColor=COLOR_TEXT,
        spaceBefore=0,
        spaceAfter=6,
        wordWrap="CJK",
    )
    return {
        "title": ParagraphStyle(
            "title", parent=base, fontName=FONT_BOLD, fontSize=22,
            leading=30, textColor=COLOR_BRAND, alignment=0, spaceAfter=4,
        ),
        "subtitle": ParagraphStyle(
            "subtitle", parent=base, fontSize=10, leading=15,
            textColor=COLOR_MUTED, spaceAfter=2,
        ),
        "h1": ParagraphStyle(
            "h1", parent=base, fontName=FONT_BOLD, fontSize=16,
            leading=24, textColor=COLOR_BRAND, spaceBefore=14, spaceAfter=8,
            keepWithNext=True,
        ),
        "h2": ParagraphStyle(
            "h2", parent=base, fontName=FONT_BOLD, fontSize=13,
            leading=20, textColor=COLOR_BRAND, spaceBefore=12, spaceAfter=6,
            keepWithNext=True,
        ),
        "h3": ParagraphStyle(
            "h3", parent=base, fontName=FONT_BOLD, fontSize=11.5,
            leading=18, textColor=COLOR_TEXT, spaceBefore=8, spaceAfter=4,
            keepWithNext=True,
        ),
        "body": base,
        "li": ParagraphStyle(
            "li", parent=base, leftIndent=14, bulletIndent=0,
            spaceAfter=3,
        ),
        "li_sub": ParagraphStyle(
            "li_sub", parent=base, leftIndent=30, bulletIndent=16,
            spaceAfter=2, fontSize=10, leading=15,
        ),
        "quote": ParagraphStyle(
            "quote", parent=base, leftIndent=10, fontSize=10,
            leading=15, textColor=COLOR_MUTED, spaceBefore=0, spaceAfter=2,
        ),
        "cell": ParagraphStyle(
            "cell", parent=base, fontSize=9.5, leading=14, spaceAfter=0,
        ),
        "cell_head": ParagraphStyle(
            "cell_head", parent=base, fontName=FONT_BOLD, fontSize=9.5,
            leading=14, spaceAfter=0,
        ),
        "footer": ParagraphStyle(
            "footer", parent=base, fontSize=8.5, leading=12,
            textColor=COLOR_MUTED, alignment=1,
        ),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Markdown 파서 (필요한 요소만)
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class Block:
    kind: str
    data: object


ORDERED_RE = re.compile(r"^(\d+)\.\s+(.*)$")
SUB_BULLET_RE = re.compile(r"^\s{2,}-\s+(.*)$")
INDENT_CONT_RE = re.compile(r"^\s{2,}(\S.*)$")


def parse_markdown(text: str) -> list[Block]:
    lines = text.splitlines()
    blocks: list[Block] = []
    i = 0
    n = len(lines)

    def is_table_row(s: str) -> bool:
        return s.lstrip().startswith("|")

    while i < n:
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        if stripped.startswith("# "):
            blocks.append(Block("h1", stripped[2:].strip()))
            i += 1
            continue
        if stripped.startswith("## "):
            blocks.append(Block("h2", stripped[3:].strip()))
            i += 1
            continue
        if stripped.startswith("### "):
            blocks.append(Block("h3", stripped[4:].strip()))
            i += 1
            continue

        if stripped == "---":
            blocks.append(Block("hr", None))
            i += 1
            continue

        if stripped.startswith("> "):
            quote_lines = [stripped[2:].strip()]
            i += 1
            while i < n and lines[i].lstrip().startswith("> "):
                quote_lines.append(lines[i].lstrip()[2:].strip())
                i += 1
            blocks.append(Block("quote", quote_lines))
            continue

        if is_table_row(line):
            rows = []
            while i < n and is_table_row(lines[i]):
                rows.append(lines[i])
                i += 1
            cells = []
            for row in rows:
                parts = [c.strip() for c in row.strip().strip("|").split("|")]
                cells.append(parts)
            header = None
            body = cells
            if len(cells) >= 2 and all(set(c.replace(":", "")) <= set("- ") for c in cells[1]):
                header = cells[0]
                body = cells[2:]
            blocks.append(Block("table", (header, body)))
            continue

        m = ORDERED_RE.match(stripped)
        if m and not line.startswith(" "):
            items = []
            while i < n:
                cur = lines[i]
                mo = ORDERED_RE.match(cur.strip())
                if mo and not cur.startswith(" "):
                    items.append({"num": mo.group(1), "text": mo.group(2).strip(), "subs": []})
                    i += 1
                    continue
                sub = SUB_BULLET_RE.match(cur)
                if sub and items:
                    items[-1]["subs"].append(sub.group(1).strip())
                    i += 1
                    continue
                cont = INDENT_CONT_RE.match(cur)
                if cont and items and not sub:
                    items[-1]["text"] += " " + cont.group(1).strip()
                    i += 1
                    continue
                if not cur.strip():
                    break
                break
            blocks.append(Block("ol", items))
            continue

        if stripped.startswith("- "):
            items = []
            while i < n:
                cur = lines[i]
                if cur.lstrip().startswith("- ") and not cur.startswith(" "):
                    items.append(cur.lstrip()[2:].strip())
                    i += 1
                    continue
                cont = INDENT_CONT_RE.match(cur)
                if cont and items and not cur.lstrip().startswith("- "):
                    items[-1] += " " + cont.group(1).strip()
                    i += 1
                    continue
                break
            blocks.append(Block("ul", items))
            continue

        para_lines = [stripped]
        i += 1
        while i < n:
            nxt = lines[i]
            ns = nxt.strip()
            if not ns:
                break
            if (
                ns.startswith("#")
                or ns.startswith("> ")
                or ns == "---"
                or is_table_row(nxt)
                or (ns.startswith("- ") and not nxt.startswith(" "))
                or (ORDERED_RE.match(ns) and not nxt.startswith(" "))
            ):
                break
            para_lines.append(ns)
            i += 1
        blocks.append(Block("p", " ".join(para_lines)))

    return blocks


# ──────────────────────────────────────────────────────────────────────────────
# 인라인 → reportlab 마크업
# ──────────────────────────────────────────────────────────────────────────────

def xml_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def inline(text: str) -> str:
    out = xml_escape(text)
    out = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", out)
    # 링크는 텍스트만 노출 (내부 경로 /legal/privacy 같은 것은 의미 없음)
    out = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"<b>\1</b>", out)
    out = re.sub(
        r"`([^`]+)`",
        r'<font color="#0f4c81"><b>\1</b></font>',
        out,
    )
    return out


# ──────────────────────────────────────────────────────────────────────────────
# 블록 → Flowable
# ──────────────────────────────────────────────────────────────────────────────

def build_flowables(
    blocks: list[Block], styles: dict[str, ParagraphStyle], available_width: float
) -> list:
    flows = []
    for blk in blocks:
        if blk.kind == "h1":
            flows.append(Paragraph(inline(blk.data), styles["h1"]))
            flows.append(HRFlowable(width="100%", thickness=0.6, color=COLOR_RULE,
                                    spaceBefore=2, spaceAfter=8))
        elif blk.kind == "h2":
            flows.append(Paragraph(inline(blk.data), styles["h2"]))
        elif blk.kind == "h3":
            flows.append(Paragraph(inline(blk.data), styles["h3"]))
        elif blk.kind == "p":
            flows.append(Paragraph(inline(blk.data), styles["body"]))
        elif blk.kind == "hr":
            flows.append(Spacer(1, 4))
            flows.append(HRFlowable(width="100%", thickness=0.4, color=COLOR_RULE,
                                    spaceBefore=2, spaceAfter=6))
        elif blk.kind == "quote":
            txt = "<br/>".join(inline(l) for l in blk.data)
            p = Paragraph(txt, styles["quote"])
            tbl = Table(
                [[p]],
                colWidths=[available_width],
            )
            tbl.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), COLOR_QUOTE_BG),
                ("LINEBEFORE", (0, 0), (0, -1), 2, COLOR_QUOTE_BAR),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]))
            flows.append(tbl)
            flows.append(Spacer(1, 6))
        elif blk.kind == "ol":
            for it in blk.data:
                txt = f'<b>{it["num"]}.</b>  {inline(it["text"])}'
                flows.append(Paragraph(txt, styles["li"]))
                for sub in it["subs"]:
                    flows.append(Paragraph(
                        f'•  {inline(sub)}', styles["li_sub"]
                    ))
            flows.append(Spacer(1, 2))
        elif blk.kind == "ul":
            for it in blk.data:
                flows.append(Paragraph(
                    f'•  {inline(it)}', styles["li"]
                ))
            flows.append(Spacer(1, 2))
        elif blk.kind == "table":
            header, body = blk.data
            ncols = max(len(r) for r in ([header] if header else []) + body)

            col_ratios = _column_ratios(header, body, ncols)
            total = sum(col_ratios)
            widths = [available_width * (r / total) for r in col_ratios]

            data = []
            if header:
                data.append([Paragraph(inline(c), styles["cell_head"]) for c in header])
            for row in body:
                padded = row + [""] * (ncols - len(row))
                data.append([Paragraph(inline(c), styles["cell"]) for c in padded])

            t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
            style = [
                ("FONTNAME", (0, 0), (-1, -1), FONT_REG),
                ("FONTSIZE", (0, 0), (-1, -1), 9.5),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("GRID", (0, 0), (-1, -1), 0.35, COLOR_TABLE_BORDER),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
            if header:
                style.append(("BACKGROUND", (0, 0), (-1, 0), COLOR_TABLE_HEAD_BG))
                style.append(("FONTNAME", (0, 0), (-1, 0), FONT_BOLD))
            t.setStyle(TableStyle(style))
            flows.append(t)
            flows.append(Spacer(1, 6))
    return flows


def _column_ratios(header, body, ncols: int) -> list[float]:
    """텍스트 길이 평균을 기반으로 컬럼 폭 비율 추정."""
    sums = [0] * ncols
    counts = [0] * ncols
    rows = []
    if header:
        rows.append(header)
    rows.extend(body)
    for row in rows:
        for idx, cell in enumerate(row[:ncols]):
            sums[idx] += max(len(cell), 1)
            counts[idx] += 1
    avgs = [(sums[i] / counts[i]) if counts[i] else 1 for i in range(ncols)]
    # 최소 폭 보장
    min_ratio = max(avgs) * 0.15
    return [max(a, min_ratio) for a in avgs]


# ──────────────────────────────────────────────────────────────────────────────
# 문서 빌드
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class DocMeta:
    title: str
    subtitle: str
    effective: str
    version: str
    issued: str
    out_path: Path


def _page_decorations(canvas, doc, meta: DocMeta):
    canvas.saveState()
    width, height = A4
    # 상단 브랜드 바
    canvas.setFillColor(COLOR_BRAND)
    canvas.rect(0, height - 8 * mm, width, 8 * mm, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont(FONT_BOLD, 9.5)
    canvas.drawString(18 * mm, height - 6 * mm, "Denvia")
    canvas.setFont(FONT_REG, 9)
    canvas.drawRightString(width - 18 * mm, height - 6 * mm, meta.title)

    # 하단 푸터
    canvas.setFillColor(COLOR_MUTED)
    canvas.setFont(FONT_REG, 8.5)
    footer_y = 12 * mm
    canvas.drawString(18 * mm, footer_y, f"{meta.title}  ·  버전 {meta.version}  ·  시행일 {meta.effective}")
    canvas.drawRightString(width - 18 * mm, footer_y, f"{doc.page}")
    canvas.setStrokeColor(COLOR_RULE)
    canvas.setLineWidth(0.3)
    canvas.line(18 * mm, footer_y + 4 * mm, width - 18 * mm, footer_y + 4 * mm)
    canvas.restoreState()


def build_pdf(md_path: Path, meta: DocMeta) -> None:
    text = md_path.read_text(encoding="utf-8")
    blocks = parse_markdown(text)

    # 상단 frontmatter(blockquote)는 별도 처리 — 본문 첫 블록에서 제외하고
    # 표제 박스로 따로 그린다.
    body_blocks = [b for b in blocks if b.kind != "quote"]
    # 첫 H1은 표지로 쓰므로 제외
    if body_blocks and body_blocks[0].kind == "h1":
        body_blocks = body_blocks[1:]

    styles = make_styles()

    page_w, page_h = A4
    left = 20 * mm
    right = 20 * mm
    top = 22 * mm
    bottom = 22 * mm
    frame_width = page_w - left - right
    frame_height = page_h - top - bottom

    doc = BaseDocTemplate(
        str(meta.out_path),
        pagesize=A4,
        leftMargin=left,
        rightMargin=right,
        topMargin=top,
        bottomMargin=bottom,
        title=meta.title,
        author="Denvia",
    )
    frame = Frame(left, bottom, frame_width, frame_height,
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
                  showBoundary=0)
    template = PageTemplate(
        id="main",
        frames=[frame],
        onPage=lambda c, d: _page_decorations(c, d, meta),
    )
    doc.addPageTemplates([template])

    flows = []
    # 표지 블록
    flows.append(Paragraph(meta.title, styles["title"]))
    flows.append(Paragraph(meta.subtitle, styles["subtitle"]))
    flows.append(Spacer(1, 6))
    info_data = [[
        Paragraph(f'<b>시행일자</b>  {meta.effective}', styles["subtitle"]),
        Paragraph(f'<b>버전</b>  {meta.version}', styles["subtitle"]),
        Paragraph(f'<b>발행</b>  {meta.issued}', styles["subtitle"]),
    ]]
    info_tbl = Table(info_data, colWidths=[frame_width / 3] * 3)
    info_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), COLOR_QUOTE_BG),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LINEABOVE", (0, 0), (-1, 0), 1.5, COLOR_BRAND),
    ]))
    flows.append(info_tbl)
    flows.append(Spacer(1, 14))

    flows.extend(build_flowables(body_blocks, styles, frame_width))

    doc.build(flows)


# ──────────────────────────────────────────────────────────────────────────────
# 엔트리
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    terms_meta = DocMeta(
        title="Denvia 이용약관",
        subtitle="치과 보험청구 및 데스크 행정업무 정보 안내 AI 보조 서비스",
        effective="2026-04-30 (제10조 2026-05-20 / 제4조 제2항 2026-05-26 시행 예정)",
        version="0.3",
        issued="2026-06-05",
        out_path=OUT_DIR / "Denvia_이용약관_v0.3_2026-06-05.pdf",
    )
    privacy_meta = DocMeta(
        title="Denvia 개인정보 처리방침",
        subtitle="회원 개인정보 수집·이용·보관·파기에 관한 사항",
        effective="2026-04-30 (선택 수집 항목 신설 2026-05-26 시행 예정)",
        version="0.2",
        issued="2026-06-05",
        out_path=OUT_DIR / "Denvia_개인정보처리방침_v0.2_2026-06-05.pdf",
    )

    build_pdf(DOCS / "terms.md", terms_meta)
    print(f"  · {terms_meta.out_path}")
    build_pdf(DOCS / "privacy.md", privacy_meta)
    print(f"  · {privacy_meta.out_path}")
    print("완료.")


if __name__ == "__main__":
    main()

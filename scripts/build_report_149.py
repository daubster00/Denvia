# -*- coding: utf-8 -*-
"""#149 대화 이어가기 — 고객 전달용 개발 완료 보고서 생성.

프로젝트 규칙 준수: SDT/콘텐츠컨트롤/문서보호/폼필드를 일절 쓰지 않는다.
python-docx 기본 요소(문단·표·목록)만 사용하므로 어떤 워드에서도 자유롭게 편집된다.
"""
from docx import Document
from docx.shared import Pt, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn

FONT = "맑은 고딕"
PURPLE = RGBColor(0x6D, 0x28, 0xD9)
GRAY = RGBColor(0x5A, 0x5A, 0x61)
DARK = RGBColor(0x17, 0x17, 0x19)

doc = Document()

# 기본 스타일
st = doc.styles["Normal"]
st.font.name = FONT
st.font.size = Pt(10.5)
st.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
st.paragraph_format.space_after = Pt(6)
st.paragraph_format.line_spacing = 1.45

for s in doc.sections:
    s.left_margin = Cm(2.4)
    s.right_margin = Cm(2.4)
    s.top_margin = Cm(2.2)
    s.bottom_margin = Cm(2.2)


def _font(run, size=10.5, bold=False, color=DARK):
    run.font.name = FONT
    run.font.size = Pt(size)
    run.bold = bold
    run.font.color.rgb = color
    run._element.rPr.rFonts.set(qn("w:eastAsia"), FONT)


def title(text, sub=None):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(2)
    _font(p.add_run(text), 20, True, DARK)
    if sub:
        q = doc.add_paragraph()
        q.paragraph_format.space_after = Pt(16)
        _font(q.add_run(sub), 10.5, False, GRAY)


def h1(text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(18)
    p.paragraph_format.space_after = Pt(6)
    _font(p.add_run(text), 14, True, PURPLE)


def h2(text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(3)
    _font(p.add_run(text), 11.5, True, DARK)


def para(text, color=DARK, size=10.5, indent=0):
    p = doc.add_paragraph()
    if indent:
        p.paragraph_format.left_indent = Cm(indent)
    _font(p.add_run(text), size, False, color)
    return p


def rich(parts, indent=0):
    """parts = [(텍스트, 굵게?), ...]"""
    p = doc.add_paragraph()
    if indent:
        p.paragraph_format.left_indent = Cm(indent)
    for text, bold in parts:
        _font(p.add_run(text), 10.5, bold, DARK)
    return p


def bullet(text, bold_head=None):
    p = doc.add_paragraph(style="List Bullet")
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.line_spacing = 1.4
    if bold_head:
        _font(p.add_run(bold_head), 10.5, True, DARK)
    _font(p.add_run(text), 10.5, False, DARK)


def table(headers, rows, widths=None):
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.LEFT
    hdr = t.rows[0].cells
    for i, h in enumerate(headers):
        hdr[i].text = ""
        p = hdr[i].paragraphs[0]
        p.paragraph_format.space_after = Pt(2)
        _font(p.add_run(h), 10, True, DARK)
    for row in rows:
        cells = t.add_row().cells
        for i, val in enumerate(row):
            cells[i].text = ""
            p = cells[i].paragraphs[0]
            p.paragraph_format.space_after = Pt(2)
            _font(p.add_run(str(val)), 10, False, DARK)
    if widths:
        for r in t.rows:
            for i, w in enumerate(widths):
                r.cells[i].width = Cm(w)
    doc.add_paragraph().paragraph_format.space_after = Pt(0)
    return t


# ══════════════════════════════════════════════════════════════════════════
title(
    "Denvia 챗봇 — 대화 이어가기 기능 개발 완료 보고",
    "수정요청 게시판 #149  ·  2026년 11월 4일  ·  운영 서버 적용 완료",
)

h1("1. 한 줄 요약")
rich([
    ("이제 챗봇이 ", False),
    ("앞서 나눈 대화를 기억하고 이어서 답변", True),
    ("합니다. 질문할 때마다 처음부터 다시 설명하지 않으셔도 됩니다.", False),
])

h1("2. 무엇이 달라졌나요")

h2("이전 방식")
para("질문 한 건마다 완전히 새로 시작했습니다. 앞에서 무엇을 물었는지 챗봇이 기억하지 "
     "못해서, 매번 내용을 전부 포함해 질문해야 했습니다.", GRAY)

h2("지금 방식")
para("최근 대화를 참고해 이어서 답변합니다. 실제 운영에서 확인한 대화입니다.")

table(
    ["순서", "질문", "답변"],
    [
        ["1", "임플란트 보험은 몇 살부터 가능해?", "보험임플란트는 만 65세부터 가능해요."],
        ["2", "그럼 1953년생이면 보험 받을 수 있는거야?",
         "1953년생이면 2026년 기준 만 65세 이상이라 나이 조건은 충족해요. "
         "다만 부분무치악이어야 하고 다른 요건도 충족해야 합니다."],
    ],
    widths=[1.2, 5.6, 8.4],
)
rich([
    ("2번 질문에는 ", False),
    ("'임플란트'라는 말이 한 글자도 없습니다.", True),
    (" 그런데도 앞 대화를 이어받아 임플란트 나이 조건으로 정확히 답했습니다.", False),
])

h1("3. 보내주신 질문에 대한 답변")

para("게시판에 이런 우려를 남겨주셨습니다.", GRAY)
q = doc.add_paragraph()
q.paragraph_format.left_indent = Cm(0.6)
q.paragraph_format.space_before = Pt(4)
q.paragraph_format.space_after = Pt(10)
_font(q.add_run(
    "“2턴에서는 이전 질문·답변만 넘어가고 참고문서는 새로 검색된다. 후속 질문이 "
    "1턴의 명사를 빼고 질문하면 엉뚱한 문서가 걸려서 잘못된 답이 나오지 않나?”\n"
    "예) ‘밥은 무슨색이야?’ → ‘하얀색?’ → ‘눈은 하얀색입니다’ (오답)"), 10, False, GRAY)

h2("정확한 지적이셨고, 그 지점은 막아두었습니다")
rich([("맞는 부분: ", True),
      ("1턴의 참고문서는 2턴으로 넘기지 않습니다. 질문·답변 글만 넘어갑니다. "
       "보험 기준은 질문마다 그에 맞는 근거 문서가 필요하고, 앞선 문서를 그대로 끌고 "
       "가면 주제가 바뀐 다음 질문에서 오히려 더 위험하기 때문입니다.", False)])

rich([("다른 부분: ", True),
      ("‘하얀색?’이라는 조각 그대로 검색하지 않습니다. 문서를 찾기 전에 "
       "앞 대화를 보고 ", False),
      ("빠진 명사를 되채워 검색어를 완성하는 단계", True),
      ("를 한 번 거칩니다.", False)])

para("운영 서버에서 실제로 확인한 변환 결과입니다.")
table(
    ["사용자가 입력한 말", "실제로 검색에 쓰인 문장"],
    [
        ["하얀색?  (앞 대화: 밥은 무슨색이야?)", "밥 색깔이 하얀색인지"],
        ["그럼 치주질환 있으면?", "스케일링 시 치주질환이 있으면 산정 기준"],
        ["65세 미만은?", "임플란트 보험 적용 조건 65세 미만"],
        ["오늘 날씨 어때?", "(주제가 바뀐 질문으로 판단해 앞 대화를 끊음)"],
    ],
    widths=[7.0, 8.2],
)

h2("검색에 쓰는 문장과 AI에게 보여주는 질문을 따로 둡니다")
para("문서는 완성된 문장으로 찾고, AI가 답할 질문 자리에는 "
     "사용자가 실제로 입력한 말을 그대로 넣습니다. 다듬은 문장으로 바꿔치기하면 "
     "사용자가 묻지 않은 것에 답하거나 뉘앙스가 달라질 수 있기 때문입니다.")

h1("4. 애매하면 답하지 않고 되묻습니다")

para("위 ‘검색어 완성’ 단계가 서버 지연이나 외부 서비스 장애로 실패할 수 있습니다. "
     "그때 조각 질문이 그대로 검색되면 염려하신 상황이 실제로 생깁니다. "
     "그래서 안전장치를 하나 더 두었습니다.")

rich([("치과 보험청구에서 틀린 기준을 안내하면 삭감·환수로 이어지므로, "
       "확실하지 않을 때는 ", False),
      ("답을 만들지 않고 되묻는 쪽", True),
      ("을 택했습니다.", False)])

h2("되묻는 경우")
bullet("‘그 경우에는?’, ‘그럼 어떻게 돼?’ 처럼 앞 대화를 받는 말만 있을 때")
bullet("‘몇 번까지 돼?’ 처럼 숫자만 묻고 대상이 빠졌을 때")
bullet("‘나는 검정색이 좋아’ 처럼 보험청구와 무관한 말일 때")

h2("되묻지 않는 경우")
bullet("첫 질문 — 이 판단 자체를 하지 않습니다")
bullet("‘초진료?’, ‘본인부담금?’ 처럼 항목 이름이 있으면 짧아도 그대로 답합니다")
bullet("‘PRR이 뭔가요’, ‘NiTi는 몇 번 넣을 수 있지?’ 처럼 현장 영문 약어가 있을 때")
bullet("‘피판작성술’, ‘급성치관주위염’ 같은 전문용어가 있을 때")

h2("되묻는 문구")
qq = doc.add_paragraph()
qq.paragraph_format.left_indent = Cm(0.6)
qq.paragraph_format.space_before = Pt(4)
_font(qq.add_run(
    "“어떤 항목에 대한 질문인지 조금만 더 적어주세요. 예를 들어 ‘스케일링 산정 기준’ "
    "처럼 항목 이름을 함께 적어주시면 정확하게 안내할 수 있어요.”"), 10, False, GRAY)

para("실제 고객 질문 1,000건으로 점검해, 정상적인 치과 질문이 잘못 되묻기로 "
     "떨어지지 않는지 확인했습니다. 오히려 기존보다 불필요한 되묻기가 줄었습니다.", GRAY, 10)

h1("5. 속도와 비용")

table(
    ["항목", "결과"],
    [
        ["첫 질문", "기존과 동일 (추가 단계 없음)"],
        ["이어지는 질문", "약 2초 추가 — 검색어를 완성하는 판단이 한 번 들어갑니다"],
        ["비용", "질문 1건당 1원 안팎. 판단 단계는 답변 생성 비용의 약 1/15 수준"],
        ["되묻는 경우", "문서 검색과 답변 생성을 하지 않아 더 저렴합니다"],
    ],
    widths=[4.0, 11.2],
)

h1("6. 함께 반영한 사항")

bullet("기존 ‘질문은 이어지지 않습니다’ 안내 팝업을 제거했습니다. "
       "이제 대화가 이어지므로 맞지 않는 안내입니다.", "안내 팝업 삭제 — ")
bullet("‘최근 몇 번의 대화까지 참고할지’(기본 5회)를 관리자 설정에서 조정할 수 있습니다.",
       "참고 범위 조정 — ")
bullet("관리자 설정에서 ‘앞선 대화를 참고해서 답변하기’를 끄면 "
       "즉시 예전 방식으로 되돌아갑니다.", "즉시 되돌리기 — ")

h1("7. 적용 현황")

table(
    ["항목", "상태"],
    [
        ["운영 서버 적용", "2026년 11월 4일 완료"],
        ["데이터베이스 변경", "적용 완료 (기존 데이터 영향 없음)"],
        ["동작 확인", "운영 서버에서 실제 대화로 확인 완료"],
        ["되돌리기", "관리자 설정 스위치 하나로 즉시 가능"],
    ],
    widths=[4.6, 10.6],
)

para("추가로 로그인·비밀번호 찾기 화면의 안내 문구를 보강하는 작업이 "
     "11월 5일 새벽에 함께 반영될 예정입니다. 서비스 이용에는 영향이 없습니다.", GRAY, 10)

h1("8. 사용하실 때 참고")

bullet("이어서 물으실 때는 평소처럼 짧게 물으셔도 됩니다. "
       "‘그럼 65세 미만은?’ 같은 식으로 충분합니다.")
bullet("주제를 바꾸실 때는 항목 이름을 함께 적어주시면 가장 정확합니다. "
       "예) ‘스케일링 산정 기준’")
bullet("되묻는 메시지가 나오면 항목 이름만 덧붙여 다시 보내주시면 됩니다.")
bullet("이상하게 답하는 사례를 발견하시면 질문 내용과 시각을 알려주세요. "
       "해당 기록을 바로 확인할 수 있습니다.")

doc.add_paragraph()
foot = doc.add_paragraph()
foot.alignment = WD_ALIGN_PARAGRAPH.CENTER
_font(foot.add_run("문의 사항은 수정요청 게시판 #149에 댓글로 남겨주시면 확인하겠습니다."),
      9.5, False, GRAY)

OUT = r"D:\projects\Dental Chatbot\자료\Denvia_대화이어가기_개발완료보고_2026-11-04.docx"
doc.save(OUT)
print("저장:", OUT)

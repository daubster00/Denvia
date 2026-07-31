import re

# ================== 🦷 3분의1악 / 2분의1악 정의 ==================

THIRDS = {
    "상악우측구치부": {18, 17, 16, 15, 14},
    "상악전치부": {13, 12, 11, 21, 22, 23},
    "상악좌측구치부": {24, 25, 26, 27, 28},
    "하악좌측구치부": {38, 37, 36, 35, 34},
    "하악전치부": {33, 32, 31, 41, 42, 43},
    "하악우측구치부": {44, 45, 46, 47, 48},
}

# 2분의1악 병합조건: 8번(사랑니) 제외 7개 치식이 정확히 일치해야 함
HALVES_7 = {
    "상악우측": {11, 12, 13, 14, 15, 16, 17},
    "상악좌측": {21, 22, 23, 24, 25, 26, 27},
    "하악좌측": {31, 32, 33, 34, 35, 36, 37},
    "하악우측": {41, 42, 43, 44, 45, 46, 47},
}

# 임상순서 (치식 범위 표기를 실제 치아 나열로 풀기 위함)
UPPER_SEQUENCE = [18, 17, 16, 15, 14, 13, 12, 11, 21, 22, 23, 24, 25, 26, 27, 28]
LOWER_SEQUENCE = [48, 47, 46, 45, 44, 43, 42, 41, 31, 32, 33, 34, 35, 36, 37, 38]

_TOOTH_NC = r'(?:1[1-8]|2[1-8]|3[1-8]|4[1-8])'   # 비캡처용
_PREFIX = r'(?:#|치아\s*)?'     # '#16' 또는 '치아16' / '치아 16' 등
_LEFT_BOUND = r'(?<!\d)'        # 앞에 숫자가 더 있으면 매칭 안 함 (예: '116'의 일부로 매칭 방지)

# normalize_query()가 짧은 숫자+조사를 붙여버리는 경우(예: '24랑', '24와')를 위한 조사 화이트리스트
# 나이/기간 단위(세,개월,년 등)와 구분하기 위해 문법 조사만 등록
_JOSA_LIST = [
    "에서는", "에서도", "으로는", "으로도", "이랑은", "이랑도",
    "에서", "으로", "이랑", "처럼", "만큼", "부터", "까지",
    "에게", "한테", "보다", "마저", "조차", "밖에",
    "은", "는", "이", "가", "을", "를", "의", "에",
    "와", "과", "랑", "도", "만", "요",
]
_JOSA_ALT = "|".join(re.escape(j) for j in sorted(_JOSA_LIST, key=len, reverse=True))

# 치식 토큰 하나: '번'이 붙으면 뒤에 조사(과/와/는 등)가 와도 허용,
# '번' 없이 맨숫자면 뒤에 조사가 오는 것도 허용(전처리 과정에서 붙어버리는 경우 대응),
# 그 외 숫자나 한글(나이·기간 단위 등)이 바로 붙는 경우만 차단
# → '16번과', '24랑', '24와'는 매칭 O / '16세','17개월'처럼 나이·기간 표현은 매칭 X
_TOOTH_TOKEN = (
    _LEFT_BOUND + _PREFIX +
    r'(' + _TOOTH_NC + r')' +
    r'(?:\s*번(?!\d)|(?=(?:' + _JOSA_ALT + r'))|(?!\d)(?![가-힣]))'
)

TOOTH_RANGE_PATTERN = re.compile(_TOOTH_TOKEN + r'\s*[~\-–]\s*' + _TOOTH_TOKEN)
TOOTH_SINGLE_PATTERN = re.compile(_TOOTH_TOKEN)

# 트리거 요인 3가지 (a, b, c 각 그룹에서 1개 이상씩 매칭되어야 작동)
TRIGGER_A = ["치주낭", "치주낭측정"]   # 치주낭측정검사 관련 키워드
TRIGGER_C = ["몇", "회", "횟수"]       # 산정/횟수 관련 키워드
# TRIGGER_B(치식)는 키워드가 아니라 실제 치식 패턴 매칭 여부로 판단 (extract_teeth_from_query 결과)


# ================== 🦷 치식 파싱 ==================

def resolve_tooth_range(a: int, b: int):
    """범위 표기(예: 34~47)를 임상순서에 따라 실제 치아 리스트로 변환"""
    for seq in (UPPER_SEQUENCE, LOWER_SEQUENCE):
        if a in seq and b in seq:
            i, j = seq.index(a), seq.index(b)
            lo, hi = min(i, j), max(i, j)
            return seq[lo:hi + 1]
    # 상하악에 걸친 비정상 범위 등 예외 케이스
    return [a, b]


def extract_teeth_from_query(query: str):
    """질문 문자열에서 치식 전체를 추출 (범위 표기 + 단일/콤마 나열 모두 처리)"""
    teeth = []
    consumed_spans = []

    for m in TOOTH_RANGE_PATTERN.finditer(query):
        a, b = int(m.group(1)), int(m.group(2))
        teeth.extend(resolve_tooth_range(a, b))
        consumed_spans.append(m.span())

    remaining = query
    for start, end in sorted(consumed_spans, reverse=True):
        remaining = remaining[:start] + " " + remaining[end:]

    for m in TOOTH_SINGLE_PATTERN.finditer(remaining):
        teeth.append(int(m.group(1)))

    return teeth


# ================== 🦷 횟수 산정 ==================

def calc_periodontal_count(teeth):
    """
    3분의1악별 산정 후, 정확히 2개 부위가 걸렸고
    그 치아 전체가 하나의 2분의1악(8번 제외 7개)과 정확히 일치하면 1.5회로 병합.
    그 외에는 부위별 비율 단순합산.
    """
    third_counts = {}
    for name, tooth_set in THIRDS.items():
        matched = sorted(set(t for t in teeth if t in tooth_set))
        if not matched:
            continue
        ratio = 0.5 if len(matched) <= 2 else 1.0
        third_counts[name] = (ratio, matched)

    if len(third_counts) == 2:
        combined = set()
        for ratio, matched in third_counts.values():
            combined.update(matched)
        for half_name, half_teeth in HALVES_7.items():
            if combined == half_teeth:
                return 1.5, {
                    "방식": "2분의1악 병합",
                    "부위": half_name,
                    "치아": sorted(combined),
                }

    total = round(sum(r for r, _ in third_counts.values()), 2)
    return total, {"방식": "3분의1악 단순합산", "부위별": third_counts}


def is_periodontal_pocket_query(query: str, teeth: list) -> bool:
    """3가지 트리거 요인이 각각 1개 이상씩 모두 충족되어야 True
    a: 치주낭/치주낭측정 키워드
    b: 치식 패턴 (teeth 리스트로 판단)
    c: 몇/회/횟수 키워드
    """
    has_a = any(kw in query for kw in TRIGGER_A)
    has_b = len(teeth) > 0
    has_c = any(kw in query for kw in TRIGGER_C)
    return has_a and has_b and has_c


def get_periodontal_result(query: str):
    """트리거 a,b,c 3가지가 모두 확인되면 (count, detail) 튜플 반환, 아니면 None"""
    teeth = extract_teeth_from_query(query)
    if not is_periodontal_pocket_query(query, teeth):
        return None
    return calc_periodontal_count(teeth)


def build_periodontal_llm_prompt(raw_query: str, count, detail: dict) -> str:
    """
    LLM에게 넘길 프롬프트를 만든다.
    오직 '사용자 질문'과 '이미 계산된 값'만 전달하고,
    값을 수정·누락 없이 그대로 출력하라는 지시만 포함한다.
    (계산근거, 부위별 내역 등 부가 설명은 넘기지 않는다)
    """
    prompt = f"""사용자의 질문: {raw_query}

사용자의 질문에 대한 계산 값은: {count}회입니다. 해당 값을 수정, 누락 없이 그대로 출력하세요."""
    return prompt


# ================== 🦷 테스트 ==================
if __name__ == "__main__":
    tests = [
        "11~17 치주낭측정검사 몇 회야?",
        "21~17 치주낭측정검사 몇 회야?",
        "34~47 치주낭측정검사 청구 몇 회?",
        "#16~11 #43~33 치주낭측정검사 몇회야?",
        "#13 ~ 24랑 #12, 11 치주낭 검사했는데 몇회로 청구해?",
    ]
    for q in tests:
        print(f"\nQ: {q}")
        print(get_periodontal_result(q))

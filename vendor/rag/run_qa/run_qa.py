from dotenv import load_dotenv
load_dotenv()

import sys
import os
import json
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from langchain_community.vectorstores import FAISS
from langchain_community.callbacks import get_openai_callback
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_classic.chains import RetrievalQA  # langchain 1.2+ 호환 (langchain_classic으로 이동, 동일 클래스)
from langchain_core.prompts import PromptTemplate  # langchain 1.2+ 호환 (langchain_core로 이동, 동일 클래스)


# ================== 🔁 동의어 ==================

def load_synonym_dict(path=None):
    if path is None:
        path = os.environ.get(
            "SYNONYMS_PATH",
            os.path.join(BASE_DIR, "config", "synonyms.json"),
        )
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# 조사 리스트 (복합 조사 포함, 긴 것 우선 정렬)
JOSA = sorted([
    "에서는", "에서도", "으로는", "으로도", "이랑은", "이랑도",
    "에서", "으로", "이랑", "처럼", "만큼", "부터", "까지",
    "에게", "한테", "보다", "마저", "조차", "밖에",
    "은", "는", "이", "가", "을", "를", "의", "에",
    "와", "과", "랑", "도", "만", "요",
], key=len, reverse=True)

# 마커: PHASE1/2에서 치환된 결과를 감싸 PHASE3에서 건너뛰게 함
_MARKER_START = "\x02"
_MARKER_END = "\x03"

# ── 위험 동의어: 부분매칭(startswith) 시 오변환 위험이 높은 짧은 한글 동의어 ──
# 이 set에 등록된 동의어는 완전 일치만 허용하고, 어미 부분매칭을 차단함
_PARTIAL_MATCH_BLACKLIST = frozenset([
    "실", "봉합", "인상", "힐링", "아테로", "바브드", "바버드",
    "잇몸", "충치", "뿌리", "세팅", "셋팅", "덴처", "덴쳐", "클라스",
])


def preprocess(text):
    """소문자 변환, 제어문자 제거, 공백 정규화"""
    text = text.lower()
    text = re.sub(r'[\x00-\x1f\x7f]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def split_token_josa(token):
    """토큰 끝의 조사를 분리. 긴 조사부터 매칭."""
    for j in JOSA:
        if token.endswith(j) and len(token) > len(j):
            return token[:-len(j)], j
    return token, ""


def build_synonym_map(synonyms):
    """
    synonym → key 역매핑.
    자기참조 제외, 충돌 시 긴 키 우선.
    """
    syn_map = {}
    for key, syn_list in synonyms.items():
        for syn in syn_list:
            syn_lower = syn.lower()
            if syn_lower == key.lower():
                continue
            if syn_lower in syn_map:
                existing_key = syn_map[syn_lower]
                if len(key) > len(existing_key):
                    syn_map[syn_lower] = key
            else:
                syn_map[syn_lower] = key
    return syn_map


def _has_symbol(text):
    """알파벳, 한글, 숫자, 공백 이외의 기호가 포함되어 있는지"""
    return bool(re.search(r'[^a-zA-Z가-힣0-9\s]', text))


def _is_english(text):
    """순수 영문 알파벳으로만 구성되어 있는지"""
    return bool(re.fullmatch(r'[a-zA-Z]+', text))


def _try_synonym_replace(token, syn_map):
    """
    토큰 → 동의어 치환.

    매칭 우선순위:
      0) 원본 토큰 완전 일치 (조사 분리 전)
      1) 조사 분리 후 완전 일치
      1-1) 영문 약어 + 한글 접미 (예: "cf하고" → "근관충전하고")
      2) 공백 제거 후 완전 일치
      3) 한글 어미 부분매칭 (영문 차단, 블랙리스트 차단)
    """
    # 0. 원본 토큰 완전 일치 (조사 분리 전)
    if token in syn_map:
        return syn_map[token]

    # 1. 조사 분리 후 완전 일치
    base, josa = split_token_josa(token)
    if base in syn_map:
        return syn_map[base] + josa

    # 1-1. 영문 약어(1~4글자) + 한글 접미 케이스
    #   예: "endo는" → base="endo는"→split→base="endo",josa="는" (위에서 처리됨)
    #   예: "cf하고" → base="cf하고"→split→base="cf하고",josa="" → 여기서 처리
    #   예: "ext했어요" → base="ext했어요"→split→base="ext했어",josa="요"
    eng_kor_match = re.match(r'^([a-zA-Z]{1,5})([가-힣]+)$', base)
    if eng_kor_match:
        eng_part, kor_part = eng_kor_match.groups()
        if eng_part in syn_map:
            return syn_map[eng_part] + kor_part + josa

    # 2글자 이하 base: syn_map에 존재하면 치환, 없으면 즉시 반환 (부분매칭 차단)
    if len(base) <= 2:
        # 이미 위에서 완전 일치 체크했으므로 여기선 None
        return None

    # 2. 공백 제거 후 완전 일치
    base_clean = base.replace(" ", "")
    for syn, key in syn_map.items():
        if len(syn) <= 2:
            continue
        if base_clean == syn.replace(" ", ""):
            return key + josa

    # 3. 한글 어미 부분매칭 (영문 차단)
    if _is_english(base):
        return None

    for syn in sorted(syn_map.keys(), key=len, reverse=True):
        # 1글자 동의어: 부분매칭 완전 차단
        if len(syn) <= 1:
            continue
        # 영문 동의어: 부분매칭 차단 (영문은 완전 일치만)
        if _is_english(syn):
            continue
        # 블랙리스트에 있으면 차단
        if syn in _PARTIAL_MATCH_BLACKLIST:
            continue
        if base.startswith(syn) and len(base) > len(syn):
            replacement_key = syn_map[syn]
            # 순환 방지: 치환 결과가 원래 base로 시작하면 스킵
            # 예: "임플"→"임플란트"인데 base가 "임플란트"이면 오변환
            if base.startswith(replacement_key) or replacement_key.startswith(base):
                continue
            suffix = base[len(syn):]
            return replacement_key + suffix + josa

    # 접미(suffix) 부분매칭 fallback — 게시판 #108 (클라이언트 최신 run_qa 반영)
    for syn in sorted(syn_map.keys(), key=len, reverse=True):
        if len(syn) <= 1 or _is_english(syn) or syn in _PARTIAL_MATCH_BLACKLIST:
            continue
        if base.endswith(syn) and len(base) > len(syn):
            rk = syn_map[syn]
            if base.endswith(rk) or rk.endswith(base):
                continue
            prefix = base[:-len(syn)]
            if len(prefix) >= 2 and re.fullmatch(r'[가-힣]+', prefix):
                return prefix + rk + josa

    return None


# ================== 🔁 스케일링 규칙 ==================

# SC/스케일링 표기 후보 — 뒤에 영문/숫자가 붙으면 매칭 차단(게시판 #136)
# "sc"가 "scaling"/"score"/"disc" 등 영어 단어 안에서 치석제거로 오치환되던 것을 방지.
_SC_ALT = r'(?:sc|s\.c|s/c|스케일링|스켈링)(?![a-zA-Z0-9])'


def apply_scaling_rules(text):
    """
    스케일링/SC 관련 동의어를 문맥에 따라 올바른 용어로 치환.
    normalize_query 이전에 원본에 적용.
    ※ preprocess(lower) 전에 호출되므로 대소문자 무시 플래그 사용.

    게시판 #136 — 클라이언트 최신 run_qa 반영: 모든 SC 후보에 영문/숫자 경계
    (_SC_ALT 의 뒤쪽 (?![a-zA-Z0-9]) + 단독 룰의 앞쪽 (?<![a-zA-Z0-9]))를 추가해
    영어 단어 속 "sc"가 치석제거로 오치환되는 문제를 차단.
    """
    # 🔥 치주
    text = re.sub(
        r'(치주)\s*(' + _SC_ALT + r')',
        r'\1치석제거', text, flags=re.IGNORECASE
    )
    # 🔥 전악
    text = re.sub(
        r'(전악)\s*(' + _SC_ALT + r')',
        r'\1치석제거', text, flags=re.IGNORECASE
    )
    # 🔥 부분
    text = re.sub(
        r'(부분)\s*(' + _SC_ALT + r')',
        r'\1치석제거', text, flags=re.IGNORECASE
    )
    # 🔥 건강/의료 보험 SC → 공백 정리만 (치환 없음, 다음 룰들이 처리)
    text = re.sub(
        r'(건강|의료)(보험)\s*(' + _SC_ALT + r')',
        r'\1 \2\3', text, flags=re.IGNORECASE
    )
    # 🔥 연1회 보험/급여 SC → 연1회치석제거
    text = re.sub(
        r'(연\s*1\s*회)\s*(보험|급여)\s*(' + _SC_ALT + r')',
        r'\1치석제거', text, flags=re.IGNORECASE
    )
    # 🔥 연1회
    text = re.sub(
        r'(연\s*1\s*회)\s*(' + _SC_ALT + r')',
        r'\1치석제거', text, flags=re.IGNORECASE
    )
    # 🔥 보험/급여 → 연1회치석제거 (단, "비보험"/"비급여"는 제외)
    text = re.sub(
        r'(?<!비)(보험|급여)\s*(' + _SC_ALT + r')',
        r'연1회치석제거', text, flags=re.IGNORECASE
    )
    # 🔥 기본 (단독 스케일링/스켈링/s.c/s/c/sc → 치석제거)
    text = re.sub(
        r'(?<![a-zA-Z0-9])' + _SC_ALT,
        '치석제거', text, flags=re.IGNORECASE
    )
    return text


def preprocess_boundary(text: str) -> str:
    """한/영 경계에 공백 삽입 — 게시판 #108 (클라이언트 최신 run_qa 반영)."""
    text = re.sub(r'([가-힣])([a-zA-Z])', r'\1 \2', text)
    text = re.sub(r'([a-zA-Z])([가-힣])', r'\1 \2', text)
    return text


# ================== 🔁 normalize_query ==================

def normalize_query(query, synonyms):
    """
    사용자 질문을 정규화.

    파이프라인:
      0) apply_scaling_rules (호출 전에 외부에서 실행)
      1) preprocess (소문자, 공백 정규화)
      2) PHASE 1: 기호 포함 동의어 직접 치환 + 마커 보호
      3) PHASE 2: 멀티워드 동의어 (공백 포함) + 마커 보호
      4) PHASE 3: 토큰 단위 치환 (마커 영역 건너뜀)
      5) 출력 정리 (괄호, 기호 주변 공백)

    게시판 #108 — 클라이언트 최신 run_qa 메인 루프의 전처리(괄호 정리 +
    한/영 경계 공백삽입 preprocess_boundary)를 normalize_query 진입부로 흡수.
    웹의 모든 호출 경로(stream/rule)가 동일 파이프라인을 공유하게 한 것이며,
    괄호 정리·경계 공백 모두 멱등(idempotent)이라 재적용해도 결과가 동일하다.
    """
    query = re.sub(r'\s*\(\s*', '(', query)
    query = re.sub(r'\s*\)\s*', ')', query)
    query = preprocess_boundary(query)
    query = preprocess(query)
    syn_map = build_synonym_map(synonyms)

    # ========================================
    # PHASE 1: 기호 포함 동의어 — 원본에서 직접 치환
    # "c/f", "p/e", "i&d", "r.f", "b.r" 등
    # 치환 결과를 마커로 감싸서 PHASE 3에서 재치환 방지
    # ========================================
    symbol_syns = {syn: key for syn, key in syn_map.items() if _has_symbol(syn)}

    for syn in sorted(symbol_syns, key=len, reverse=True):
        key = symbol_syns[syn]
        pattern = re.escape(syn)
        # 영문/숫자가 바로 붙으면 차단 (오매칭 방지), 한글 경계는 두지 않음
        bounded_pattern = (
            r'(?<![a-zA-Z0-9])'
            + pattern
            + r'(?![a-zA-Z0-9])'
        )
        replacement = _MARKER_START + key + _MARKER_END
        query = re.sub(bounded_pattern, replacement, query, flags=re.IGNORECASE)

    # ========================================
    # PHASE 2: 멀티워드 동의어 (공백 포함)
    # "final setting", "수술 후 처치" 등
    # ========================================
    multi_word_syns = {syn: key for syn, key in syn_map.items()
                       if " " in syn and not _has_symbol(syn)}

    for syn in sorted(multi_word_syns, key=len, reverse=True):
        key = multi_word_syns[syn]
        pattern = re.escape(syn)
        replacement = _MARKER_START + key + _MARKER_END
        query = re.sub(pattern, replacement, query, flags=re.IGNORECASE)

    # ========================================
    # PHASE 3: 토큰 단위 치환
    # 마커로 감싸진 부분은 건너뜀
    # ========================================
    token_pattern = re.compile(
        r'(' + re.escape(_MARKER_START) + r'.*?' + re.escape(_MARKER_END) + r')'
        r'|(#[a-zA-Z0-9]+)'
        r'|([가-힣a-zA-Z0-9]+)'
        r'|([^\s가-힣a-zA-Z0-9' + re.escape(_MARKER_START) + re.escape(_MARKER_END) + r'])'
    )

    tokens = token_pattern.findall(query)
    normalized_tokens = []

    for marker_group, tooth_group, word_group, symbol_group in tokens:
        if marker_group:
            # 마커 제거하고 치환된 결과만 추가
            value = marker_group.replace(_MARKER_START, '').replace(_MARKER_END, '')
            normalized_tokens.append(value)
        elif tooth_group:
            # 치식 번호 (#11, #i26 등) — 동의어 치환 없이 보존
            normalized_tokens.append(tooth_group)
        elif symbol_group:
            normalized_tokens.append(symbol_group)
        elif word_group:
            result = _try_synonym_replace(word_group, syn_map)
            if result is not None:
                normalized_tokens.append(result)
            else:
                normalized_tokens.append(word_group)

    # 결합 및 공백/기호 정리
    output = " ".join(normalized_tokens)

    # 괄호 주변 공백 정리
    output = re.sub(r'\s*\(\s*', '(', output)
    output = re.sub(r'\s*\)\s*', ')', output)
    output = re.sub(r'\)([가-힣a-zA-Z])', r') \1', output)

    # 기호 주변 공백 정리
    output = re.sub(r'\s*([/,.\?!])\s*', r'\1', output)
    output = re.sub(r',(\S)', r', \1', output)

    return output


# ================== 🔥 장애인가산 룰 ==================

PATTERNS = {
    "보통처치": r"보통\s*처치(?:시행|했|진행|실시)?",
    "치아진정처치": r"치아\s*진정\s*처치(?:시행|했|진행|실시)?",
    "치아파절편제거": r"치아\s*파절편\s*제거(?:술|시행|했|진행|실시)?",
    "치수복조": r"치수\s*복조(?:시행|했|진행|실시)?",
    "지각과민처치(간단)": r"지각\s*과민\s*처치\s*\(?간단\)?(?:시행|했|진행|실시)?",
    "지각과민처치(복잡)": r"지각\s*과민\s*처치\s*\(?복잡\)?(?:시행|했|진행|실시)?",
    "지각과민처치": r"지각\s*과민\s*처치(?:술|시행|했|진행|실시)?",
    "근관와동형성": r"근관\s*와동\s*형성(?:시행|했|진행|실시)?",
    "즉일충전처치": r"즉일\s*충전\s*처치(?:시행|했|진행|실시)?",
    "당일발수근충": r"당일\s*발수\s*근충(?:시행|했|진행|실시)?",
    "치수절단": r"치수\s*절단(?:시행|했|진행|실시)?",
    "치수절단술": r"치수\s*절단술(?:시행|했|진행|실시)?",
    "발수": r"발수(?:시행|했|진행|실시)?",
    "근관세척": r"근관\s*세척(?:시행|했|진행|실시)?",
    "근관확대": r"근관\s*확대(?:시행|했|진행|실시)?",
    "근관성형": r"근관\s*성형(?:시행|했|진행|실시)?",
    "근관충전": r"근관\s*충전(?:시행|했|진행|실시)?",
    "근관치료": r"근관\s*치료(?:시행|했|진행|실시)?",
    "충전처치": r"충전\s*처치(?:시행|했|진행|실시)?",
    "gi충전": r"gi\s*충전(?:시행|했|진행|실시)?",
    "충전물연마": r"충전물\s*연마(?:시행|했|진행|실시)?",
    "러버댐": r"러버댐(?:시행|했|진행|실시)?",
    "와동형성": r"와동\s*형성(?:시행|했|진행|실시)?",
    "파절기구제거": r"파절\s*기구\s*제거(?:시행|했|진행|실시)?",
    "응급근관처치": r"응급\s*근관\s*처치(?:시행|했|진행|실시)?",
    "보철물제거(간단)": r"보철물\s*제거\s*\(?간단\)?(?:시행|했|진행|실시)?",
    "보철물제거(복잡)": r"보철물\s*제거\s*\(?복잡\)?(?:시행|했|진행|실시)?",
    "보철물제거": r"보철물\s*제거(?:시행|했|진행|실시)?",
    "근관내기존충전물제거": r"근관내\s*기존\s*충전물\s*제거(?:시행|했|진행|실시)?",
    "보철물재부착": r"보철물\s*재부착(?:시행|했|진행|실시)?",
    "금속재포스트제거": r"금속재\s*포스트\s*제거(?:시행|했|진행|실시)?",
    "포스트제거": r"포스트\s*제거(?:시행|했|진행|실시)?",
    "광중합형복합레진": r"광중합형\s*복합\s*레진(?:시행|했|진행|실시)?",
    "보험레진": r"보험\s*레진(?:시행|했|진행|실시)?",
    "수술후처치(간단)": r"수술\s*후\s*처치\s*\(?간단\)?(?:시행|했|진행|실시)?",
    "수술후처치": r"수술\s*후\s*처치(?:시행|했|진행|실시)?",
    "치주치료후처치(간단)": r"치주치료\s*후\s*처치\s*\(?간단\)?(?:시행|했|진행|실시)?",
    "치주치료후처치(복잡)": r"치주치료\s*후\s*처치\s*\(?복잡\)?(?:시행|했|진행|실시)?",
    "치주후처치": r"치주\s*후\s*처치(?:시행|했|진행|실시)?",
    "치면세마": r"치면\s*세마(?:시행|했|진행|실시)?",
    "치석제거": r"치석\s*제거(?:시행|했|진행|실시)?",
    "치근활택술": r"치근\s*활택(?:술|시행|했|진행|실시)?",
    "순열수술후보호장치": r"순열\s*수술후\s*보호장치(?:시행|했|진행|실시)?",
    "상고정장치술": r"상고정\s*장치(?:술|시행|했|진행|실시)?",
    "고정장치제거": r"고정\s*장치\s*제거(?:술|시행|했|진행|실시)?",
    "교합조정": r"교합\s*조정(?:술|시행|했|진행|실시)?",
    "수술용스플린트": r"수술용\s*스플린트(?:시행|했|진행|실시)?",
    "악간고정술": r"악간\s*고정(?:술|시행|했|진행|실시)?",
    "치간고정술": r"치간\s*고정(?:술|시행|했|진행|실시)?",
    "잠간고정술": r"잠간\s*고정(?:술|시행|했|진행|실시)?",
    "교합성형술": r"교합\s*성형(?:술|시행|했|진행|실시)?",
    "교합기부착모형상의교합성형술": r"교합기부착모형상의교합성형(?:술|시행|했|진행|실시)?",
    "행동조절": r"행동\s*조절(?:시행|했|진행|실시)?",
    "측두하악관절자극요법": r"측두\s*하악\s*관절\s*자극\s*요법(?:시행|했|진행|실시)?",
    "치면열구전색": r"치면\s*열구\s*전색(?:술|시행|했|진행|실시)?",
    "낭종감압장치술": r"낭종\s*감압\s*장치(?:술|시행|했|진행|실시)?",
    "발치": r"발치(?:술|시행|했|진행|실시)?",
    "완전매복발치": r"완전\s*매복\s*발치(?:술|시행|했|진행|실시)?",
    "복잡매복발치": r"복잡\s*매복\s*발치(?:술|시행|했|진행|실시)?",
    "단순매복발치": r"단순\s*매복\s*발치(?:술|시행|했|진행|실시)?",
    "매복발치": r"매복\s*발치(?:술|시행|했|진행|실시)?",
    "난발치": r"난\s*발치(?:술|시행|했|진행|실시)?",
    "3대구치발치": r"3\s*대구치\s*발치(?:술|시행|했|진행|실시)?",
    "발치와재소파술": r"발치와\s*재소파(?:술|시행|했|진행|실시)?",
    "치조골성형수술": r"치조골\s*성형(?:술|시행|했|진행|실시)?",
    "구강내소염수술": r"구강내\s*소염(?:술|시행|했|진행|실시)?",
    "구강외소염수술": r"구강외\s*소염(?:술|시행|했|진행|실시)?",
    "구강내열상봉합술": r"구강내\s*열상\s*봉합(?:술|시행|했|진행|실시)?",
    "협순소대성형술": r"협순\s*소대\s*성형(?:술|시행|했|진행|실시)?",
    "치성편도주위농양절개술": r"치성편도주위농양절개(?:술|시행|했|진행|실시)?",
    "악골수염수술": r"악\s*골수염(?:술|시행|했|진행|실시)?",
    "법랑아세포종적출술": r"법랑아\s*세포종\s*적출(?:술|시행|했|진행|실시)?",
    "치근낭적출술": r"치근낭\s*적출(?:술|시행|했|진행|실시)?",
    "치근단절제술": r"치근단\s*절제(?:술|시행|했|진행|실시)?",
    "구강안면누공쇄술": r"구강\s*안면\s*누공쇄(?:술|시행|했|진행|실시)?",
    "구강상악동누공폐쇄술": r"구강\s*상악동\s*누공폐쇄(?:술|시행|했|진행|실시)?",
    "치아재식술": r"치아\s*재식(?:술|시행|했|진행|실시)?",
    "치은판절제술": r"치은판\s*절제(?:술|시행|했|진행|실시)?",
    "치은-치초부병소": r"치은-치초부병소(?:시행|했|진행|실시)?",
    "종양절제술": r"종양\s*절제(?:술|시행|했|진행|실시)?",
    "탈구치아정복술": r"탈구\s*치아\s*정복(?:술|시행|했|진행|실시)?",
    "치조골골절비관혈적정복술": r"치조골\s*골절\s*비관혈적\s*정복(?:술|시행|했|진행|실시)?",
    "치조골골절관혈적정복술": r"치조골\s*골절\s*관혈적\s*정복(?:술|시행|했|진행|실시)?",
    "골융기절제술": r"골융기\s*절제(?:술|시행|했|진행|실시)?",
    "환괄골궁현수고정술": r"환괄골궁현수고정(?:술|시행|했|진행|실시)?",
    "두개안면현수공정술": r"두개안면현수공정(?:술|시행|했|진행|실시)?",
    "환하악골결찰술": r"환하악골결찰(?:술|시행|했|진행|실시)?",
    "악골내고정용금속제거술": r"악골내\s*고정용\s*금속\s*제거(?:술|시행|했|진행|실시)?",
    "임플란트제거술(간단)": r"임플란트\s*제거술\s*\(?간단\)?(?:시행|했|진행|실시)?",
    "임플란트제거술(복잡)": r"임플란트\s*제거술\s*\(?복잡\)?(?:시행|했|진행|실시)?",
    "임플란트제거술": r"임플란트\s*제거(?:술|시행|했|진행|실시)?",
    "악관절강세척술": r"악관절\s*강\s*세척(?:술|시행|했|진행|실시)?",
    "치주소파술": r"치주\s*소파(?:술|시행|했|진행|실시)?",
    "치은신부착술": r"치은신\s*부착(?:술|시행|했|진행|실시)?",
    "치은성형술": r"치은\s*성형(?:술|시행|했|진행|실시)?",
    "치은절제술": r"치은\s*절제(?:술|시행|했|진행|실시)?",
    "치은박리소파술": r"치은\s*박리\s*소파(?:술|시행|했|진행|실시)?",
    "치근면처치술": r"치근면\s*처치(?:술|시행|했|진행|실시)?",
    "치조골결손부골이식술": r"치조골\s*결손부\s*골이식(?:술|시행|했|진행|실시)?",
    "조직유도재생술": r"조직\s*유도\s*재생(?:술|시행|했|진행|실시)?",
    "조직유도재생막제거술": r"조직\s*유도\s*재생막\s*제거(?:술|시행|했|진행|실시)?",
    "치은측방변위판만술": r"치은\s*측방\s*변위판만(?:술|시행|했|진행|실시)?",
    "치간변위판막술": r"치간\s*변위\s*판막(?:술|시행|했|진행|실시)?",
    "치은이식술": r"치은\s*이식(?:술|시행|했|진행|실시)?",
    "치근절제술": r"치근\s*절제(?:술|시행|했|진행|실시)?",
    "치관확장술": r"치관\s*확장(?:술|시행|했|진행|실시)?",
    "치관분리술": r"치관\s*분리(?:술|시행|했|진행|실시)?",
    "틀니조직면개조": r"틀니\s*조직면\s*개조(?:시행|했|진행|실시)?",
    "틀니수리": r"틀니\s*수리(?:시행|했|진행|실시)?",
    "틀니조정": r"틀니\s*조정(?:시행|했|진행|실시)?",
    "클라스프수리": r"클라스프\s*수리(?:시행|했|진행|실시)?",
    "자가치아유래골이식술": r"자가치아\s*유래\s*골이식(?:술|시행|했|진행|실시)?",
}

DISABILITY_AVAILABLE = [
    "보통처치", "치아진정처치", "치아파절편제거", "치수복조",
    "지각과민처치(간단)", "지각과민처치(복잡)", "지각과민처치",
    "근관와동형성", "즉일충전처치", "당일발수근충", "치수절단술",
    "발수", "근관세척", "근관확대", "근관성형", "근관충전", "근관치료",
    "충전처치", "gi충전", "충전물연마", "러버댐", "와동형성",
    "파절기구제거", "응급근관처치",
    "보철물제거(간단)", "보철물제거(복잡)", "보철물제거",
    "근관내기존충전물제거", "보철물재부착",
    "금속재포스트제거", "포스트제거",
    "광중합형복합레진", "보험레진",
    "수술후처치(간단)", "수술후처치",
    "치주치료후처치(간단)", "치주치료후처치(복잡)", "치주후처치", "치주치료후처치",
    "치면세마", "치석제거", "치근활택술",
    "순열수술후보호장치", "상고정장치술", "고정장치제거",
    "교합조정", "수술용스플린트",
    "악간고정술", "치간고정술", "잠간고정술",
    "교합성형술", "교합기부착모형상의교합성형술",
    "행동조절", "측두하악관절자극요법", "치면열구전색", "낭종감압장치술",
    "발치", "완전매복발치", "복잡매복발치", "단순매복발치", "매복발치",
    "난발치", "3대구치발치", "발치와재소파술",
    "치조골성형수술", "구강내소염수술", "구강외소염수술",
    "구강내열상봉합술", "협순소대성형술", "치성편도주위농양절개술",
    "악골수염수술", "법랑아세포종적출술", "치근낭적출술", "치근단절제술",
    "구강안면누공쇄술", "구강상악동누공폐쇄술",
    "치아재식술", "치은판절제술", "치은-치초부병소",
    "종양절제술", "탈구치아정복술",
    "치조골골절비관혈적정복술", "치조골골절관혈적정복술",
    "골융기절제술", "환괄골궁현수고정술", "두개안면현수공정술",
    "환하악골결찰술", "악골내고정용금속제거술",
    "임플란트제거술(간단)", "임플란트제거술(복잡)", "임플란트제거술",
    "악관절강세척술",
    "치주소파술", "치은신부착술", "치은성형술", "치은절제술", "치은박리소파술",
    "치근면처치술", "치조골결손부골이식술",
    "조직유도재생술", "조직유도재생막제거술",
    "치은측방변위판만술", "치간변위판막술", "치은이식술",
    "치근절제술", "치관확장술", "치관분리술",
    "틀니조직면개조", "틀니수리", "틀니조정", "클라스프수리",
    "자가치아유래골이식술", "치수절단",
]

TEMPLATE_OK = """장애인가산 적용이 가능한 뇌병변 장애인, 지적장애인, 정신장애인, 자폐성 장애인이 치과에 내원하여 {procedures}를 진행한 경우 {procedures}는 장애인가산적용되는 행위임으로 해당 행위에 대한 행위료는 300%가산이 적용돼요. 이때 시각장애인,청각장애인,지체장애인은 장애인 가산적용 불가능합니다~  """

TEMPLATE_NO = """{procedure}행위는 장애인가산적용 가능한 항목 88개에 없어 장애인가산적용이 불가합니다.추가적으로 시각장애인,청각장애인,지체장애인은 장애인 가산적용 불가해요... """

TEMPLATE_MULTI = """장애인가산적용이 가능한 행위 2가지 이상을 동시실시한 경우 장애인가산은 중복적용되지 않아 1회만 산정되어 행위료 300% 가산 적용되며,이때 시각장애인,청각장애인,지체장애인은 장애인 가산적용 불가능합니다~ """


def extract_procedures(query):
    matches = []
    for name, pattern in PATTERNS.items():
        if re.search(pattern, query):
            matches.append(name)

    # 긴 단어 먼저
    matches = sorted(matches, key=len, reverse=True)

    selected = []
    # 겹치는거 제거
    for m in matches:
        if not any(m in s or s in m for s in selected):
            selected.append(m)
    return selected


def format_procedures(procedures):
    if len(procedures) == 1:
        return procedures[0]
    elif len(procedures) == 2:
        return f"{procedures[0]}와 {procedures[1]}"
    else:
        return ", ".join(procedures[:-1]) + f"와 {procedures[-1]}"


def generate_rule_answer(query):
    procedures = extract_procedures(query)

    if not procedures:
        return None

    valid = []
    invalid = []

    for p in procedures:
        if p in DISABILITY_AVAILABLE:
            if p not in valid:
                valid.append(p)
        else:
            invalid.append(p)

    results = []

    if valid:
        proc_text = format_procedures(valid)
        results.append(TEMPLATE_OK.format(procedures=proc_text))
        if len(valid) >= 2:
            results.append(TEMPLATE_MULTI)

    if invalid:
        for p in invalid:
            results.append(TEMPLATE_NO.format(procedure=p))

    return "\n".join(results)


# =====================================================


# ================== 🔥 벡터 로드 (lazy init) ==================
# ADR-0002 허용 수정 (iv): import 시 즉시 실행 → lazy init
# ADR-0002 허용 수정 (ii): cwd 상대 경로 → 환경변수 주입
_embeddings = None
_vectorstore = None
_retriever = None
_syn_dict = None


def _get_faiss_path():
    return os.environ.get(
        "FAISS_CURRENT_PATH",
        os.path.join(BASE_DIR, "..", "..", "api", "data", "faiss", "current"),
    )


def _get_syn_path():
    return os.environ.get(
        "SYNONYMS_PATH",
        os.path.join(BASE_DIR, "config", "synonyms.json"),
    )


def init_rag(faiss_path=None, syn_path=None):
    """FAISS 인덱스와 동의어 사전을 초기화한다 (idempotent)."""
    global _embeddings, _vectorstore, _retriever, _syn_dict
    if faiss_path is None:
        faiss_path = _get_faiss_path()
    if syn_path is None:
        syn_path = _get_syn_path()
    if _embeddings is None:
        _embeddings = OpenAIEmbeddings(model="text-embedding-3-large")
    if _retriever is None and os.path.exists(faiss_path):
        _vectorstore = FAISS.load_local(
            faiss_path, _embeddings, allow_dangerous_deserialization=True
        )
        _retriever = _vectorstore.as_retriever(search_kwargs={"k": 5})
    if _syn_dict is None:
        _syn_dict = load_synonym_dict(syn_path)


def get_retriever():
    """초기화된 retriever를 반환한다 (FAISS 미초기화 시 None)."""
    return _retriever


def get_syn_dict():
    """초기화된 동의어 사전을 반환한다."""
    if _syn_dict is None:
        init_rag()
    return _syn_dict


# ================== 🔥 질문 루프 ==================
# ADR-0002 허용 수정 (i): while True CLI 루프 → if __name__ == "__main__": 가드
if __name__ == "__main__":
    from prompt_builder import build_prompt_template

    init_rag()

    while True:
        raw_query = input("\n📝 질문을 입력하세요 (종료: exit):\n> ")

        if raw_query.lower() in ["exit", "quit"]:
            break

        # 순서: scaling_rules(원본) → normalize_query(내부에서 preprocess)
        query = apply_scaling_rules(raw_query)
        query = normalize_query(query, get_syn_dict())

        # ✅ 1. 룰 먼저 실행
        rule_answer = generate_rule_answer(query)

        has_disability = "장애인" in query
        has_gasan = "가산" in query

        if has_disability and has_gasan and (rule_answer is not None):
            print(f"\n🔍 원본 질문: {raw_query}")
            print(f"🔁 치환된 질문: {query}")
            print("\n🤖 답변:\n")
            print(rule_answer)
        else:
            # ✅ 2. 질문에 맞는 프롬프트 동적 생성 + RAG 실행
            prompt_template_str = build_prompt_template(query)

            qa_chain = RetrievalQA.from_chain_type(
                llm=ChatOpenAI(model_name="o4-mini"),
                chain_type="stuff",
                retriever=get_retriever(),
                return_source_documents=True,
                chain_type_kwargs={
                    "prompt": PromptTemplate.from_template(prompt_template_str)
                }
            )

            with get_openai_callback() as cb:
                result = qa_chain.invoke({"query": query})

            print(f"\n🔍 원본 질문: {raw_query}")
            print(f"🔁 치환된 질문: {query}")
            print("\n🤖 답변:\n")
            print(result["result"])

            print("\n🔗 관련 문서:")
            for i, doc in enumerate(result["source_documents"]):
                print(f"[{i+1}] {doc.metadata.get('category')} / {doc.metadata.get('section')}")
                print(f"\n📊 토큰 사용량: 입력 {cb.prompt_tokens:,} | 출력 {cb.completion_tokens:,} | 합계 {cb.total_tokens:,} | 비용 ${cb.total_cost:.6f}")

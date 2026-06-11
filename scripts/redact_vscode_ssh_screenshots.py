"""캡쳐된 VSCode SSH 가이드 스크린샷에서 PII / 타 클라이언트 정보 제거.

문제:
- 03: Recent files 패널에 SubRace·Dental Chatbot·Memory Bridge·한강웰니스워크 등 타 프로젝트 경로
- 06: SSH 호스트 picker에 subrace-prod-01 / Btmdesign (타 클라이언트·개인 호스트)
- 10/11/12/13: Windows 로컬 파일 다이얼로그에 사용자 본명("hyung woo jeong") + 무관

처리:
- 사용할 컷: 03 (재가공) / 05 (그대로) / 06 (재가공)
- 폐기: 01, 02, 07, 08, 09 (대부분 빈 창 또는 picker 반복), 10~13 (로컬 다이얼로그)
- 출력: outputs/vscode_ssh/clean/NN_*.png  ← docx 빌더가 참조

실행: py -3 scripts/redact_vscode_ssh_screenshots.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "outputs" / "vscode_ssh"
DST = SRC / "clean"
DST.mkdir(parents=True, exist_ok=True)

# 폰트 — 시스템 맑은 고딕
def _font(size: int) -> ImageFont.ImageFont:
    for p in (
        "C:/Windows/Fonts/malgun.ttf",
        "C:/Windows/Fonts/malgunbd.ttf",
    ):
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def annotate_arrow(img: Image.Image, *, x: int, y: int, text: str,
                   color=(255, 90, 90)) -> None:
    """원형 강조 + 화살표 + 라벨."""
    d = ImageDraw.Draw(img)
    r = 18
    d.ellipse((x - r, y - r, x + r, y + r), outline=color, width=4)
    font = _font(22)
    # 라벨은 박스 안에
    pad = 8
    bbox = d.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    lx, ly = x + r + 14, y - th // 2 - pad
    d.rectangle((lx - pad, ly - pad, lx + tw + pad, ly + th + pad),
                fill=(40, 40, 40), outline=color, width=2)
    d.text((lx, ly), text, font=font, fill=(255, 255, 255))


# ──────────────────────────────────────────────────────────────────────────────
# 03 — Welcome + Recent files. Recent 패널만 검정 사각형으로 가린 뒤 라벨.
# ──────────────────────────────────────────────────────────────────────────────
def process_03_welcome() -> None:
    src = SRC / "03_extensions_remote_ssh_search.png"
    img = Image.open(src).convert("RGB")
    d = ImageDraw.Draw(img)
    # VSCode 창은 약 (185, 70)~(775, 470) 영역. Recent 섹션은 좌하단.
    # Recent 박스 좌표 (관찰)
    rx1, ry1, rx2, ry2 = 252, 314, 410, 405
    d.rectangle((rx1, ry1, rx2, ry2), fill=(30, 30, 30))
    # 라벨
    font = _font(14)
    d.text((rx1 + 6, ry1 + 6), "(최근 파일 영역)", font=font,
           fill=(140, 140, 140))
    img.save(DST / "01_welcome.png", "PNG")
    print(f"  -> 01_welcome.png  (Recent 영역 가림)")


# ──────────────────────────────────────────────────────────────────────────────
# 05 — Command palette. PII 없음. 그대로 복사 + 강조 화살표만.
# ──────────────────────────────────────────────────────────────────────────────
def process_05_palette() -> None:
    src = SRC / "05_command_palette_remote_ssh.png"
    img = Image.open(src).convert("RGB")
    # 첫 항목 "Remote-SSH: Connect Current Window to Host..." 가 강조됨
    # Command palette 위치(관찰): 첫 항목 중심 약 (480, 28)
    annotate_arrow(img, x=600, y=29, text="이 항목 클릭")
    img.save(DST / "03_command_palette.png", "PNG")
    print(f"  -> 03_command_palette.png  (Connect 항목 화살표)")


# ──────────────────────────────────────────────────────────────────────────────
# 06 — Host picker. subrace-prod-01 / Btmdesign 두 줄 redact.
# ──────────────────────────────────────────────────────────────────────────────
def process_06_picker() -> None:
    src = SRC / "06_host_picker.png"
    img = Image.open(src).convert("RGB")
    d = ImageDraw.Draw(img)
    # Picker 박스 (관찰): 좌상 (670, 45), 우하 (1255, 165)
    # 각 항목 높이 ~22px
    # subrace-prod-01 라인: y=49~70
    # Btmdesign 라인:       y=71~92
    # denvia-prod-01 라인:  y=93~114  ← 살림
    d.rectangle((670, 49, 1255, 91), fill=(45, 45, 45))
    font = _font(15)
    d.text((690, 56), "(다른 SSH 호스트 - 가림)", font=font,
           fill=(140, 140, 140))
    # denvia-prod-01 강조
    annotate_arrow(img, x=735, y=104, text="denvia-prod-01 선택")
    img.save(DST / "04_host_picker.png", "PNG")
    print(f"  -> 04_host_picker.png  (denvia 외 호스트 가림 + 강조)")


# ──────────────────────────────────────────────────────────────────────────────
# 02 — Extensions 패널 강조본을 03 원본을 재활용해 만든다.
# 03 원본에는 좌측 사이드바에 Extensions 아이콘이 잘 보임. Extensions
# 아이콘 좌표 강조용으로 03 같은 컷 사용.
# ──────────────────────────────────────────────────────────────────────────────
def process_02_extensions_hint() -> None:
    src = SRC / "03_extensions_remote_ssh_search.png"
    img = Image.open(src).convert("RGB")
    d = ImageDraw.Draw(img)
    # Recent 영역 가림(03과 동일 처리)
    d.rectangle((252, 314, 410, 405), fill=(30, 30, 30))
    # 좌측 사이드바 Extensions 아이콘 위치 — VSCode 안쪽 좌측 (관찰)
    # 안쪽 vscode 창 좌상단 ~ (185, 90), 사이드바 아이콘들 세로 (105, 125, 145, 170, 195)
    # Extensions 아이콘 (네번째): 약 (197, 195)
    annotate_arrow(img, x=197, y=195, text="Extensions 클릭")
    img.save(DST / "02_extensions_icon.png", "PNG")
    print(f"  -> 02_extensions_icon.png  (Extensions 아이콘 강조)")


def main() -> None:
    process_03_welcome()
    process_02_extensions_hint()
    process_05_palette()
    process_06_picker()
    print(f"\nclean 출력 디렉터리: {DST}")
    for p in sorted(DST.glob("*.png")):
        print(f"  {p.name}  ({p.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()

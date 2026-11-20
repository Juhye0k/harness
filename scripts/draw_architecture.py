"""Build the README diagram with uv run --group docs python scripts/draw_architecture.py."""

from base64 import b64encode
from html import escape
from pathlib import Path

import resvg_py

OUT = Path(__file__).resolve().parents[1] / "docs"
PINK = "#FF0866"
PURPLE = "#8452ED"
TEAL = "#008E94"
GREEN = "#77991B"
ORANGE = "#EE7B00"
INK = "#273347"
GRAY = "#526173"
parts = [
    '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
    'width="1450" height="960" viewBox="0 0 1450 960" role="img" aria-labelledby="title desc">',
    '<title id="title">Shortform System Architecture · 숏폼 제작 백엔드</title>',
    '<desc id="desc">FastAPI가 작업을 기록하고 Redis로 ID를 발행한다. Celery 워커가 '
    "분석과 출력을 처리하고 PostgreSQL과 공유 볼륨에 결과를 기록한다. YouTube 전송은 "
    "별도 승인과 전용 워커를 거친다.</desc>",
    '<defs><linearGradient id="pink" x2="0" y2="1"><stop stop-color="#FF6398"/>'
    '<stop offset="1" stop-color="#FF005B"/></linearGradient></defs>',
    '<rect width="1450" height="960" fill="white"/>',
    '<g font-family="Malgun Gothic, Noto Sans CJK KR, Noto Sans KR, sans-serif">',
]


def text(x, y, value, size=19, color=INK, weight=400, anchor="start"):
    parts.append(
        f'<text x="{x}" y="{y}" fill="{color}" font-size="{size}" '
        f'font-weight="{weight}" text-anchor="{anchor}">{escape(value)}</text>'
    )


def box(x, y, w, h, color, fill="white", dashed=False):
    dash = ' stroke-dasharray="7 6"' if dashed else ""
    parts.append(
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="22" '
        f'stroke="{color}" fill="{fill}" stroke-width="2.5"{dash}/>'
    )


def pill(x, y, w, label, color):
    parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="40" rx="20" fill="{color}"/>')
    text(x + w / 2, y + 27, label, 19, "white", 700, "middle")


def mark(x, y, filename, size=48):
    data = b64encode((OUT / "architecture-marks" / filename).read_bytes()).decode("ascii")
    mime = "image/svg+xml" if filename.endswith(".svg") else "image/png"
    parts.append(
        f'<image x="{x}" y="{y}" width="{size}" height="{size}" '
        f'xlink:href="data:{mime};base64,{data}"/>'
    )


def arrow(points, color):
    coords = " ".join(f"{x},{y}" for x, y in points)
    x, y = points[-1]
    prev_x, prev_y = points[-2]
    dx = (x > prev_x) - (x < prev_x)
    dy = (y > prev_y) - (y < prev_y)
    parts.append(
        f'<g fill="none" stroke="{color}" stroke-width="2.5" stroke-linejoin="round">'
        f'<polyline points="{coords}"/><path d="M{x - 10 * dx + 6 * dy} {y - 10 * dy - 6 * dx} '
        f'L{x} {y} L{x - 10 * dx - 6 * dy} {y - 10 * dy + 6 * dx}"/></g>'
    )


pill(30, 22, 450, "Shortform System Architecture", "url(#pink)")
text(32, 105, "숏폼 제작 백엔드", 32, INK, 700)
text(32, 140, "영상 입력부터 전사·후보 추천, 자막 편집과 세로 MP4 출력까지", 21, GRAY)
arrow([(950, 54), (1005, 54)], PINK)
text(1020, 61, "HTTP 요청", 18, GRAY)
arrow([(1160, 54), (1215, 54)], TEAL)
text(1230, 61, "비동기 작업", 18, GRAY)

box(231, 196, 1189, 524, INK, dashed=True)
pill(254, 176, 365, "Local Development · Docker Compose", INK)
mark(634, 143, "compose.svg", 50)

box(22, 310, 168, 200, PINK, "#FFF6FA")
text(106, 353, "브라우저", 25, PINK, 700, "middle")
for i, line in enumerate(["영상 링크 · 파일", "후보 · 자막 편집", "상태 조회", "결과 다운로드"]):
    text(106, 391 + 29 * i, line, 17, INK, anchor="middle")

box(261, 271, 280, 258, GREEN)
pill(281, 251, 176, "API / HTTP", GREEN)
box(280, 318, 242, 175, ORANGE)
mark(304, 334, "fastapi.svg")
text(367, 368, "FastAPI", 27, INK, 700)
text(401, 422, "입력 검증 · 작업 접수", 19, anchor="middle")
text(401, 458, "ID로 상태·결과 조회", 18, GRAY, anchor="middle")
arrow([(190, 405), (280, 405)], PINK)

box(580, 271, 296, 413, PURPLE)
pill(600, 251, 221, "Data & Broker", PURPLE)
box(602, 318, 251, 125, ORANGE)
mark(628, 334, "redis.svg")
text(696, 368, "Redis", 27, INK, 700)
text(727, 414, "큐에 작업 ID 전달", 19, anchor="middle")
arrow([(522, 382), (602, 382)], TEAL)
box(602, 526, 251, 134, ORANGE)
mark(620, 538, "postgresql.png")
text(678, 572, "PostgreSQL", 24, INK, 700)
text(727, 611, "작업 상태 · 전사 · 후보", 18, anchor="middle")
text(727, 638, "자막 버전 · 게시 상태", 18, anchor="middle")
arrow([(401, 493), (401, 593), (602, 593)], PURPLE)
text(274, 626, "접수 기록 · 상태 조회", 17, PURPLE)

box(924, 271, 465, 413, TEAL)
pill(944, 251, 230, "Processing Worker", TEAL)
mark(945, 295, "celery.png", 52)
text(1009, 331, "Celery 워커", 27, INK, 700)
box(947, 355, 418, 75, TEAL, "#F5FCFC")
text(968, 386, "analysis 큐 · 음성 전사", 21, TEAL, 700)
text(968, 414, "추천 모드에서 후보를 생성하고 채점", 17)
box(947, 444, 418, 82, TEAL, "#F5FCFC")
text(968, 476, "video 큐 · 파일 검증과 영상 출력", 21, TEAL, 700)
text(968, 505, "10초·후보 추출 또는 확정 자막으로 세로 출력", 17)
arrow([(853, 382), (947, 382)], TEAL)
arrow([(900, 382), (900, 484), (947, 484)], TEAL)
arrow([(924, 602), (853, 602)], PURPLE)
text(900, 633, "기록", 16, PURPLE, anchor="middle")
text(948, 576, "공유 파일 볼륨", 22, INK, 700)
text(948, 613, "/uploads  ·  업로드 원본", 19)
text(948, 646, "/data  ·  작업 파일과 다운로드용 MP4", 19)
text(262, 705, "AI 전사·추천은 제공자를 설정하고 활성화한 뒤 실행한다.", 16, GRAY)

box(30, 783, 1390, 150, PURPLE, "#FCFAFF")
pill(52, 763, 340, "YouTube 게시 · 별도 승인", PURPLE)
text(419, 770, "기본 비활성", 17, GRAY)
text(62, 847, "사용자와 FastAPI", 23, PURPLE, 700)
text(62, 882, "출력 버전·채널·제목·공개 범위와", 17)
text(62, 909, "아동용 여부를 확인하고 승인", 17)
arrow([(355, 855), (420, 855)], TEAL)
mark(441, 811, "redis.svg", 42)
text(495, 841, "Redis", 23, INK, 700)
text(441, 885, "sns 큐에 ID 전달", 18)
arrow([(637, 855), (701, 855)], TEAL)
mark(724, 808, "celery.png", 48)
text(787, 841, "SNS 전용 워커", 23, INK, 700)
text(724, 885, "승인한 출력과 파일 해시 대조", 18)
arrow([(1039, 855), (1101, 855)], TEAL)
mark(1122, 809, "youtube.png", 48)
text(1183, 843, "YouTube", 25, INK, 700)
text(1122, 885, "승인한 채널로 MP4 전송", 18)

parts.append("</g></svg>")
svg = "\n".join(parts) + "\n"
png = resvg_py.svg_to_bytes(svg_string=svg, zoom=2)
(OUT / "architecture.svg").write_text(svg, encoding="utf-8", newline="\n")
(OUT / "architecture.png").write_bytes(png)

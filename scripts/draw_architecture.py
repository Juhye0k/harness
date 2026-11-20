"""Build the README diagram with uv run --group docs python scripts/draw_architecture.py."""

from html import escape
from pathlib import Path

import resvg_py

OUT = Path(__file__).resolve().parents[1] / "docs"
INK = "#152E40"
BODY = "#304D5D"
BLUE = "#195C89"
TEAL = "#116C63"
PLUM = "#75436A"
parts = [
    '<svg xmlns="http://www.w3.org/2000/svg" width="1040" height="990" '
    'viewBox="0 0 1040 990" role="img" aria-labelledby="title desc" lang="ko">',
    '<title id="title">숏폼 제작 백엔드</title>',
    '<desc id="desc">FastAPI가 요청을 기록하고 Redis로 식별자를 전달한다. Celery 워커가 '
    "분석과 영상 출력을 처리한다. PostgreSQL은 업무 상태를, 공유 볼륨은 파일을 저장한다. "
    "YouTube 전송은 별도 승인과 SNS 워커를 거친다.</desc>",
    '<rect width="1040" height="990" fill="#FAFCFD"/>',
    '<g font-family="Malgun Gothic, Noto Sans CJK KR, Noto Sans KR, sans-serif">',
]


def text(x, y, value, size=19, color=BODY, weight=400):
    parts.append(
        f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" '
        f'fill="{color}">{escape(value)}</text>'
    )


def card(x, y, w, h, title, lines, color=BLUE, fill="white"):
    parts.append(
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" '
        f'fill="{fill}" stroke="#B8CAD3" stroke-width="1.5"/>'
    )
    text(x + 18, y + 35, title, 23, color, 700)
    for index, line in enumerate(lines):
        text(x + 18, y + 67 + 27 * index, line)


def path(d, color):
    parts.append(
        f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2.5" '
        'stroke-linejoin="round" stroke-linecap="round"/>'
    )


def arrow(x1, x2, y, color=BLUE):
    path(f"M{x1} {y} H{x2} m-7 -5 7 5 -7 5", color)


def section(y, title, color):
    text(32, y, title, 25, color, 700)


text(32, 56, "숏폼 제작 백엔드", 40, INK, 700)
text(32, 93, "브라우저에서 작업을 접수하고, 반환된 ID로 상태와 결과를 조회한다.", 21)
section(154, "작업 접수와 Celery 비동기 처리", BLUE)

card(
    32,
    229,
    215,
    148,
    "브라우저",
    ["영상 링크 또는 파일", "후보 선택 · 자막 편집", "원음 확인 후 출력"],
)
arrow(247, 271, 303)
card(272, 229, 200, 148, "FastAPI", ["입력 검증", "작업을 DB에 기록", "작업 ID 발행"])
arrow(472, 496, 303)
card(497, 248, 152, 111, "Redis", ["작업 ID 전달"], fill="#EAF4FA")

path("M649 303 H673 M673 235 V373", BLUE)
arrow(673, 700, 235)
arrow(673, 700, 373)
card(
    701,
    175,
    307,
    125,
    "analysis 큐 → 분석 워커",
    ["음성 전사", "추천 모드에서 후보 생성·채점"],
    fill="#EAF4FA",
)
card(
    701,
    312,
    307,
    150,
    "video 큐 → 영상 워커",
    ["업로드 검증 · 10초 추출", "선택한 후보 구간 추출", "확정 자막으로 세로 MP4 출력"],
    fill="#EAF4FA",
)
text(32, 446, "전사·추천은 AI 제공자를 설정하고 활성화한 뒤 실행한다.", 18)

section(522, "API와 워커가 공유하는 저장소", TEAL)
card(
    32,
    547,
    474,
    137,
    "PostgreSQL  ·  업무 상태의 기준",
    [
        "작업 상태 · 전사 · 추천 후보 · 자막 편집 버전",
        "API는 상태를 조회하고 워커는 처리 결과를 기록",
    ],
    TEAL,
    "#EBF6F3",
)
card(
    524,
    547,
    484,
    137,
    "공유 파일 볼륨  ·  영상 데이터",
    ["/uploads · 업로드한 원본", "/data · 작업 파일과 다운로드용 MP4"],
    TEAL,
    "#EBF6F3",
)

section(752, "YouTube 게시 승인", PLUM)
text(289, 751, "선택 기능 · 기본 비활성", 18, PLUM)
card(
    32,
    778,
    351,
    160,
    "사용자 확인 → FastAPI",
    [
        "출력 버전 · 채널 · 제목 · 공개 범위",
        "아동용 여부를 포함한 초안을 확인",
        "서버가 승인 내용의 일치를 검사",
    ],
    PLUM,
)
arrow(383, 411, 854, PLUM)
card(412, 797, 172, 116, "Redis", ["sns 큐에 ID 전달"], PLUM, "#F7EEF5")
arrow(584, 612, 854, PLUM)
card(
    613,
    778,
    395,
    160,
    "SNS 전용 워커 → YouTube",
    [
        "승인한 출력과 파일 해시(SHA-256) 대조",
        "일치하는 MP4만 승인한 채널로 전송",
        "전송 상태를 PostgreSQL에 기록",
    ],
    PLUM,
    "#F7EEF5",
)

parts.append("</g></svg>")
svg = "\n".join(parts) + "\n"
png = resvg_py.svg_to_bytes(svg_string=svg, zoom=2)
(OUT / "architecture.svg").write_text(svg, encoding="utf-8", newline="\n")
(OUT / "architecture.png").write_bytes(png)

"""Generate editable SVG and a PNG preview. No external logos or private assets."""

from html import escape
from pathlib import Path

import resvg_py

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs"
PINK = "#FF0866"
PURPLE = "#8452ED"
TEAL = "#00A5AB"
GREEN = "#80A51C"
ORANGE = "#EE7B00"
INK = "#273347"
GRAY = "#667386"
parts = [
    '<svg xmlns="http://www.w3.org/2000/svg" width="1640" height="1320" '
    'viewBox="0 0 1640 1320" role="img" aria-labelledby="title desc">',
    '<title id="title">Shortform System Architecture</title>',
    '<desc id="desc">FastAPI, PostgreSQL, Redis, Celery 개발 기반과 향후 영상 분석 구조. '
    "실선은 현재 점검 연결, 점선은 구현 예정.</desc>",
    '<defs><linearGradient id="pink" x1="0" y1="0" x2="0" y2="1">'
    '<stop stop-color="#FF6398"/><stop offset="1" stop-color="#FF005B"/>'
    "</linearGradient></defs>",
    '<rect width="1640" height="1320" fill="white"/>',
    '<g font-family="Malgun Gothic, Noto Sans KR, sans-serif">',
]


def box(x, y, w, h, color, fill="white", dashed=False, radius=22):
    dash = ' stroke-dasharray="7 6"' if dashed else ""
    parts.append(
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" '
        f'fill="{fill}" stroke="{color}" stroke-width="2.5"{dash}/>'
    )


def text(x, y, value, size=18, color=INK, weight=400, anchor="start"):
    parts.append(
        f'<text x="{x}" y="{y}" fill="{color}" font-size="{size}" '
        f'font-weight="{weight}" text-anchor="{anchor}">{escape(value)}</text>'
    )


def pill(x, y, w, label, color="url(#pink)"):
    parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="40" rx="20" fill="{color}"/>')
    text(x + w / 2, y + 27, label, 17, "white", 700, "middle")


def arrow(points, color, dashed=False):
    coords = " ".join(f"{x},{y}" for x, y in points)
    dash = ' stroke-dasharray="7 6"' if dashed else ""
    parts.append(
        f'<polyline points="{coords}" fill="none" stroke="{color}" '
        f'stroke-width="2" stroke-linejoin="round"{dash}/>'
    )
    x, y = points[-1]
    px, py = points[-2]
    if x > px:
        head = [(x - 9, y - 6), (x, y), (x - 9, y + 6)]
    elif x < px:
        head = [(x + 9, y - 6), (x, y), (x + 9, y + 6)]
    elif y > py:
        head = [(x - 6, y - 9), (x, y), (x + 6, y - 9)]
    else:
        head = [(x - 6, y + 9), (x, y), (x + 6, y + 9)]
    parts.append(
        '<polyline points="'
        + " ".join(f"{a},{b}" for a, b in head)
        + f'" fill="none" stroke="{color}" stroke-width="2"/>'
    )


def label(x, y, value, color=GRAY):
    text(x, y, value, 14, color)


pill(35, 28, 570, "Shortform System Architecture")
text(38, 99, "FastAPI + PostgreSQL + Redis + Celery", 24, INK, 700)
text(38, 130, "초기 개발 기반 · 현재 설정과 향후 제품 흐름을 구분한 설계", 18, GRAY)
arrow([(1080, 42), (1150, 42)], PINK)
label(1170, 47, "HTTP / 상태 점검", PINK)
arrow([(1080, 77), (1150, 77)], TEAL)
label(1170, 82, "메시지 / 작업 실행", TEAL)
arrow([(1080, 112), (1150, 112)], GRAY, True)
label(1170, 117, "점선: 향후 구현 · 실선: 초기 연결", GRAY)

box(250, 170, 1330, 740, INK, dashed=True)
pill(280, 150, 380, "Local Development · Docker Compose", INK)
label(1140, 204, "별도 프로세스 · 하나의 코드 저장소", PURPLE)

box(290, 270, 330, 280, GREEN)
pill(310, 250, 180, "API / HTTP", GREEN)
box(320, 345, 270, 150, ORANGE)
text(455, 383, "FastAPI", 27, ORANGE, 700, "middle")
pill(342, 404, 226, "/health/live · /ready")
text(455, 474, "Pydantic · 환경 설정", 16, GRAY, anchor="middle")

box(660, 270, 310, 550, PURPLE)
pill(680, 250, 230, "Data & Broker", PURPLE)
box(690, 345, 250, 150, ORANGE)
text(815, 383, "Redis", 27, ORANGE, 700, "middle")
pill(720, 404, 190, "Task Broker", TEAL)
text(815, 474, "작은 메시지 전달", 16, GRAY, anchor="middle")
box(690, 640, 250, 135, ORANGE)
text(815, 679, "PostgreSQL", 25, ORANGE, 700, "middle")
text(815, 713, "SQLAlchemy · Alembic", 17, GRAY, anchor="middle")
text(815, 745, "현재: 연결 설정 / 업무 테이블 없음", 13, GRAY, anchor="middle")

box(1010, 270, 520, 550, TEAL)
pill(1030, 250, 250, "Processing Worker", TEAL)
box(1040, 345, 460, 150, ORANGE)
text(1270, 383, "Celery Worker", 27, ORANGE, 700, "middle")
pill(1090, 404, 360, "현재: diagnostic ping · 동시 실행 1")
text(1270, 474, "업무 작업 / 자동 복구 미구현", 16, GRAY, anchor="middle")
box(1040, 565, 460, 210, TEAL, "#F5FCFC", True)
text(1062, 598, "영상 분석·생성 파이프라인  [예정]", 20, TEAL, 700)
text(1062, 635, "음성 + 영상 + 텍스트 특징", 18)
text(1062, 670, "점수 결합 → 후보 추천 → 자막 편집", 18)
text(1062, 705, "선택한 후보 → FFmpeg → 출력 검증", 18)
text(1062, 747, "분석 버전·중간 결과 재사용으로 비용 제한", 15, GRAY)

box(30, 355, 175, 140, PINK, "#FFF6FA")
text(117, 393, "Client", 25, PINK, 700, "middle")
text(117, 425, "브라우저 / API 문서", 14, GRAY, anchor="middle")
text(117, 459, "제품 UI 연결 예정", 14, GRAY, anchor="middle")
arrow([(205, 390), (320, 390)], PINK)
label(220, 374, "HTTP", PINK)
arrow([(590, 385), (690, 385)], PINK)
label(620, 372, "PING", PINK)
arrow([(590, 460), (690, 460)], TEAL, True)
label(621, 445, "작업 ID", TEAL)
arrow([(940, 415), (1040, 415)], TEAL)
label(956, 398, "진단 소비", TEAL)
arrow([(455, 495), (455, 706), (690, 706)], PINK)
label(475, 689, "SELECT 1 · 상태 점검", PINK)
arrow([(1040, 706), (940, 706)], TEAL, True)
label(976, 689, "결과", TEAL)
arrow([(1270, 495), (1270, 565)], TEAL, True)
label(1284, 535, "업무 함수 연결 예정", TEAL)

text(290, 864, "현재 실행 범위: 상태 점검 · 워커 진단 · 로컬 인프라 · CI", 18, INK, 700)
text(
    290,
    890,
    "인증·업로드·AI 분석·렌더링·SNS 게시·업무 데이터 모델은 구현하지 않았습니다.",
    16,
    GRAY,
)

box(290, 960, 310, 130, PURPLE, "#FAF8FF", True)
text(445, 998, "Web UI  [예정]", 22, PURPLE, 700, "middle")
text(445, 1033, "후보 선택 · 자막 수정 · 다운로드", 15, GRAY, anchor="middle")
text(445, 1064, "기존 화면과 API 연결은 후속 작업", 14, GRAY, anchor="middle")
box(660, 960, 310, 130, GREEN, "#FBFDF6", True)
text(815, 998, "Object Storage  [예정]", 22, GREEN, 700, "middle")
text(815, 1033, "S3 호환 · 원본 / 미리보기 / 결과", 15, GRAY, anchor="middle")
text(815, 1064, "업로드·다운로드는 서명 URL", 14, GRAY, anchor="middle")
box(1040, 960, 460, 130, TEAL, "#F5FCFC", True)
text(1270, 998, "AI Provider / Model  [예정]", 22, TEAL, 700, "middle")
text(1270, 1033, "초기 외부 API · 이후 필요한 단계만 GPU", 16, GRAY, anchor="middle")
text(1270, 1064, "분량·동시성·재시도·예산 제한", 15, GRAY, anchor="middle")
arrow([(600, 1030), (660, 1030)], GREEN, True)
arrow([(1100, 775), (1100, 930), (815, 930), (815, 960)], GREEN, True)
label(840, 951, "영상 파일", GREEN)
arrow([(1370, 775), (1370, 960)], TEAL, True)
label(1384, 935, "모델 호출", TEAL)

box(35, 1150, 1545, 125, PURPLE, "#FCFAFF")
pill(60, 1130, 260, "Development Harness", PURPLE)
text(80, 1198, "AGENTS.md", 20, PURPLE, 700)
text(390, 1198, "uv.lock + verify.py", 20, INK, 700)
text(790, 1198, "GitHub Actions", 20, INK, 700)
text(1220, 1198, "Review / Feedback", 20, INK, 700)
arrow([(250, 1191), (365, 1191)], INK)
arrow([(610, 1191), (765, 1191)], INK)
arrow([(985, 1191), (1195, 1191)], INK)
text(80, 1240, "작업 범위·완료 조건", 16, GRAY)
text(390, 1240, "Ruff · pytest · migration 설정 검사", 16, GRAY)
text(790, 1240, "단위·통합 검사 · Docker 빌드", 16, GRAY)
text(1220, 1240, "AI 리뷰 기준 · 사람의 검토", 16, GRAY)
text(1580, 1304, "Architecture v0.1 · Setup only · 자동 배포 없음", 13, GRAY, anchor="end")
parts.append("</g></svg>")
svg = "\n".join(parts)
OUT.mkdir(exist_ok=True)
(OUT / "architecture.svg").write_text(svg, encoding="utf-8")
(OUT / "architecture.png").write_bytes(resvg_py.svg_to_bytes(svg_string=svg))
print("Generated docs/architecture.svg and docs/architecture.png")

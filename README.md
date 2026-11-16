# Shortform Harness

FastAPI + PostgreSQL + Redis + Celery 기반 숏폼 서비스입니다. **10초 추출과 한국어 전사 기반 하이라이트 추천·선택 추출**을 제공합니다. 추천 AI와 YouTube 업로드는 기본 비활성화입니다. 실제 비공개 Shorts 업로드와 Studio 분류를 확인했습니다. 실제 모델 품질은 미검증이며 자막 편집은 아직 없습니다.

**[프로젝트 위키 시작하기](https://github.com/Juhye0k/short-form/wiki)** — 문제 정의, 단계별 계획, 구조·기술 선택, 개발 하네스와 운영 절차를 카테고리별로 관리합니다.

![시스템 아키텍처](docs/architecture.png)

[아키텍처 SVG](docs/architecture.svg) · [현재 구현 현황](wiki/07-governance/status.md) · [단계별 계획](wiki/02-delivery/roadmap.md)

## 빠른 시작

### 로컬 영상 추출

Python 3.12·uv·FFmpeg·FFprobe가 필요하며, YouTube에는 Deno도 필요합니다. 도구는 PATH에 등록합니다. 이 작업 공간의 Windows 포터블 도구는 `.tmp/tools`에서 자동으로 찾으므로 바로 아래 명령을 실행할 수 있습니다. 시스템 PATH나 PowerShell 실행 정책은 변경하지 않습니다.

```powershell
uv sync --locked
uv run python -m app.cli.extract_clip --url "https://media.w3.org/2010/05/sintel/trailer.mp4" --start 5
uv run python scripts/verify.py
```

성공하면 `.artifacts/video-runs/<실행 ID>/output/clip.mp4`와 `result.json`이 생성됩니다. 링크·제한·오류·설치 방법은 [영상 추출 실행 안내](wiki/05-development/video-extraction.md)를 참고합니다. DB·Redis·Docker 없이 실행합니다.

### API·워커 개발 기반

저장소 루트에서 실행합니다. Docker Desktop의 Linux 엔진, uv와 Python 3.12가 필요합니다.

```powershell
uv sync --locked
uv run python scripts/verify.py
docker compose up --build -d
curl.exe http://localhost:8000/health/live
curl.exe http://localhost:8000/health/ready
```

API 문서: http://localhost:8000/docs

웹 화면: http://localhost:8000/ — 링크와 시작 시간을 입력하고 처리 상태·미리보기·다운로드를 확인합니다. [웹 사용·브라우저 검증 안내](wiki/05-development/web-video-extraction.md).

추천 화면: http://localhost:8000/recommendations — [설정·실행·검증 안내](wiki/05-development/highlight-recommendations.md). 실제 AI 호출에는 별도 제공자 키와 승인된 입력·예산이 필요합니다. 일반 CI는 합성 영상과 고정 AI 대역을 사용합니다.

YouTube 업로드: http://localhost:8000/sns — [OAuth 설정·확인·중복 처리 안내](wiki/05-development/youtube-upload.md). 계정·출력 버전·제목·공개 범위를 확인한 뒤 전용 워커로 전송합니다. 기본은 비공개이며 일반 CI는 제공자 대역만 사용합니다.

영상 작업은 `POST /jobs/video-extractions`로 등록합니다. 요청·조회·다운로드와 중단 작업 처리 명령은 [비동기 실행 안내](wiki/05-development/async-video-jobs.md)를 따릅니다.

준비 상태 점검은 PostgreSQL·Redis 연결만 확인합니다. 워커 실행은 별도 통합 검사로 확인합니다. Compose는 로컬 개발용이며 공개 배포 구성이 아닙니다.

## 상세 안내

| 목적 | 문서 |
|---|---|
| 처음 합류했을 때 | [온보딩](wiki/05-development/onboarding.md) |
| 시스템 이해 | [구조](wiki/03-architecture/system-overview.md), [흐름](wiki/03-architecture/runtime-flows.md) |
| 다음 개발 | [영상·작업 처리 단계](wiki/02-delivery/phase-02-video-jobs.md) |
| 검사 실행 | [검증 절차](wiki/05-development/harness/verification.md) |
| AI와 작업 | [AGENTS.md](AGENTS.md), [하네스 시작하기](wiki/05-development/harness/README.md) |
| 실행 오류 | [점검 절차](wiki/06-operations/runbook.md) |
| 문서 추가 | [문서 관리 규칙](wiki/07-governance/document-guide.md) |

## 저장소 구조

```text
app/          # API·DB·Celery 설정, 영상 CLI·규칙·서비스·외부 도구
migrations/   # Alembic 환경과 video_jobs 테이블
tests/        # unit·process·media·integration 검사와 실행 안내
scripts/      # 검사 진입점·다이어그램 생성
wiki/         # 카테고리별 프로젝트 문서
docs/         # 다이어그램과 이전 문서 링크 안내
.github/      # CI·PR 양식
```

GitHub Actions는 검사와 Docker 빌드를 실행하며 자동 배포·유료 AI 호출을 하지 않습니다. 필수 검사 병합 차단은 별도 저장소 규칙이 필요합니다.

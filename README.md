# Shortform Harness

긴 영상에서 짧게 공유할 장면을 골라 세로 영상으로 만드는 서비스입니다. **자를 위치를 알면 시작 시각을 지정해 10초를 추출합니다.** 장면을 찾아야 할 때는 한국어 음성을 글로 옮긴 전사를 바탕으로 후보를 추천받습니다. 제작실에서 후보의 원음을 듣고 자막을 고친 뒤, 확인한 편집 버전을 MP4와 자막 파일(SRT)로 내려받을 수 있습니다. [제작실 사용 흐름](https://github.com/Juhye0k/short-form/wiki/05-development-complete-flow)

백엔드를 처음 본다면 아래 CLI로 영상의 5초 지점부터 10초를 잘라 보세요. 같은 추출을 웹에서 요청하면 FastAPI는 작업 번호를 돌려주고, Celery 워커가 인코딩을 맡습니다. Redis는 작업 번호를 전달하고 PostgreSQL은 브라우저가 다시 조회할 처리 상태를 보관합니다. [요청 한 건으로 읽는 시스템 구조](https://github.com/Juhye0k/short-form/wiki/03-architecture-system-overview)

**현재 검증 범위**는 로컬 제작실과 실제 편집본 한 건의 비공개 YouTube Shorts 게시까지입니다. Studio 분류를 확인했지만 게시 제목은 사전 승인안과 달랐습니다. 같은 원본을 다시 분석했을 때 최종 후보도 한 개였습니다. 다음 과제는 어느 단계에서 후보가 줄었는지 기록하고 게시 직전 제목을 대조하는 것입니다. 추천 AI와 업로드는 기본 비활성화이며 운영 배포는 후속 단계입니다. [실제 검증과 남은 과제](https://github.com/Juhye0k/short-form/wiki/07-governance-status)

**[프로젝트 위키 시작하기](https://github.com/Juhye0k/short-form/wiki)** — 문제 정의, 단계별 계획, 구조·기술 선택, 개발 하네스와 운영 절차를 카테고리별로 관리합니다.

![시스템 아키텍처](docs/architecture.png)

[그림 원본](docs/architecture.svg)

## 로컬에서 첫 영상 추출

Python 3.12와 uv, FFmpeg·FFprobe를 준비하고 저장소 루트에서 실행하세요. 아래 공개 MP4의 5초부터 15초까지 자릅니다. YouTube 입력에는 Deno도 필요합니다.

```powershell
uv sync --locked
uv run python -m app.cli.extract_clip --url "https://media.w3.org/2010/05/sintel/trailer.mp4" --start 5
```

성공하면 `.artifacts/video-runs/<실행 ID>/output/clip.mp4`와 검사 결과를 담은 `result.json`이 생깁니다. [추출 명령과 실패 코드](https://github.com/Juhye0k/short-form/wiki/05-development-video-extraction)

## 브라우저에서 사용하기

Docker의 Linux 엔진을 켜고 아래 명령을 실행하세요.

```powershell
docker compose up --build -d
curl.exe http://localhost:8000/health/ready
```

준비 응답이 200이면 [추출 화면](http://localhost:8000/extract)에서 시작 시각을 지정하거나 [제작실](http://localhost:8000/)에서 추천 작업을 시작할 수 있습니다. 추천에는 제공자 설정이 필요합니다. [전사·추천 설정](https://github.com/Juhye0k/short-form/wiki/05-development-groq-free-ai) · [실행 환경 점검](https://github.com/Juhye0k/short-form/wiki/06-operations-runbook)

[실제 자막 겹침을 발견한 검사](https://github.com/Juhye0k/short-form/wiki/05-development-harness-records-2026-11-18-final-output-e2e) · [개발 검증 명령](https://github.com/Juhye0k/short-form/wiki/05-development-harness-verification)

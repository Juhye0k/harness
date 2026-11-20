# Shortform Harness

긴 영상에서 짧게 공유할 장면을 골라 세로 영상으로 만드는 서비스입니다. **자를 위치를 알면 시작 시각을 지정해 10초를 추출합니다.** 장면을 찾아야 할 때는 한국어 음성을 글로 옮긴 전사를 바탕으로 후보를 추천받습니다. 제작실에서 후보의 원음을 듣고 자막을 고친 뒤, 확인한 편집 버전을 MP4와 자막 파일(SRT)로 내려받을 수 있습니다. [제작실 사용 흐름](wiki/05-development/complete-flow.md)

백엔드를 처음 본다면 아래 CLI로 영상의 5초 지점부터 10초를 잘라 보세요. 같은 추출을 웹에서 요청하면 FastAPI는 작업 번호를 돌려주고, Celery 워커가 인코딩을 맡습니다. Redis는 작업 번호를 전달하고 PostgreSQL은 브라우저가 다시 조회할 처리 상태를 보관합니다. [요청 한 건으로 읽는 시스템 구조](wiki/03-architecture/system-overview.md)

**현재 검증 범위**는 로컬 제작실과 실제 편집본 한 건의 비공개 YouTube Shorts 게시까지입니다. Studio 분류를 확인했지만 게시 제목은 사전 승인안과 달랐습니다. 같은 원본을 다시 분석했을 때 최종 후보도 한 개였습니다. 다음 과제는 어느 단계에서 후보가 줄었는지 기록하고 게시 직전 제목을 대조하는 것입니다. 추천 AI와 업로드는 기본 비활성화이며 운영 배포는 후속 단계입니다. [실제 검증과 남은 과제](wiki/07-governance/status.md)

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

쇼츠 제작실: http://localhost:8000/ — 링크 또는 파일로 시작하고, 내 프로젝트에서 작업을 다시 열어 후보 미리보기·자막 편집·다운로드·YouTube 게시까지 진행합니다. [전체 사용 흐름](wiki/05-development/complete-flow.md).

10초 추출: http://localhost:8000/extract — 링크와 시작 시간을 입력하고 처리 상태·미리보기·다운로드를 확인합니다. [추출 화면 안내](wiki/05-development/web-video-extraction.md).

표시 자막과 SRT: 완료된 전사·추천 화면에서 확인·다운로드합니다. 원본 전사는 별도로 보존하며 [분할 규칙과 제한](wiki/05-development/subtitle-segmentation.md)을 확인하세요.

추천 화면: http://localhost:8000/recommendations — [설정·실행·검증 안내](wiki/05-development/highlight-recommendations.md). 실제 AI 호출에는 별도 제공자 키와 승인된 입력·예산이 필요합니다. 일반 CI는 합성 영상과 고정 AI 대역을 사용합니다.

예산 0원 프로토타입은 [Groq 무료 모드 설정](wiki/05-development/groq-free-ai.md)을 따릅니다. 무료 계정 확인과 키 설정 후 활성화하며, 한도 초과 시 유료 제공자로 자동 전환하지 않습니다.

현재 첫 실행은 **음성 전사만 확인**입니다. `TRANSCRIPTION_PROVIDER=groq`, `RECOMMENDATION_PROVIDER=none`으로 설정하면 추천 모델 없이 시간별 대사를 확인할 수 있습니다.

YouTube 업로드: http://localhost:8000/sns — [OAuth 설정·확인·중복 처리 안내](wiki/05-development/youtube-upload.md). 계정·출력 버전·제목·공개 범위를 확인한 뒤 전용 워커로 전송합니다. 기본은 비공개이며 일반 CI는 제공자 대역만 사용합니다.

영상 작업은 `POST /jobs/video-extractions`로 등록합니다. 요청·조회·다운로드와 중단 작업 처리 명령은 [비동기 실행 안내](wiki/05-development/async-video-jobs.md)를 따릅니다.

준비 상태 점검은 PostgreSQL·Redis 연결만 확인합니다. 워커 실행은 별도 통합 검사로 확인합니다. Compose는 로컬 개발용이며 공개 배포 구성이 아닙니다.

## 상세 안내

로컬 파일 입력: 추출·전사·추천 화면에서 최대 500MiB·20분 파일을 업로드하고, 원본 검증 완료 후 기존 작업에 재사용합니다. [지원 형식·전송 상태·저장·삭제 계약](wiki/05-development/local-video-upload.md)을 따릅니다.

입력부터 끝까지: [자막 편집·비동기 출력·YouTube 흐름과 엔드투엔드 검사](wiki/05-development/complete-flow.md). 원본 전사와 편집본을 분리하고, 확인한 버전으로만 최종 영상을 만듭니다. 일반 CI의 모델·YouTube는 대역이며 실제 품질·계정 게시를 보장하지 않습니다.

세로 출력만 확인하려면 `uv run python -m app.cli.render_sample`을 실행하세요. 외부 호출 없이 합성 영상으로 한국어 자막이 들어간 720×1280 MP4와 클립 기준 SRT를 만듭니다. 편집 화면에서 저장한 버전의 비동기 출력은 위 제작실에서 실행할 수 있습니다. [샘플 실행 안내와 검증 범위](wiki/05-development/portrait-subtitle-sample.md)

Google 로그인·내 자료·7일 만료는 선택 활성화 기능입니다. 기존 로컬 자료는 보존하며 로그인 계정에 자동 연결하지 않습니다. [설정·테스트 계정 승인·삭제 절차](wiki/05-development/user-auth-data.md)를 따르세요. 별도 로컬 환경에서 실제 테스트 계정의 Google 로그인·승인·로그아웃을 확인했습니다. 기존 개발 서비스의 인증 전환과 운영 배포는 별도입니다.

검증 결과: http://localhost:8000/verification — 분석 번호를 입력하거나 분석 화면의 검증 결과 링크로 이동합니다. [빠른 숏츠 자막 정책](wiki/05-development/shorts-display-policy.md)은 1줄 중심의 1~3어절·0.45~1.8초 자막을 제공합니다. 시간 정보가 불확실한 구간이 있으면 완성본 SRT 다운로드를 차단합니다.

전사 검수는 분석 결과 화면에서 의심 구간·관측값 확인, 앞뒤 음성 재생, 판정 저장과 JSON 보고서를 제공합니다. 추가 AI 호출이나 원문 수정은 하지 않습니다. [검수 정책·API·실제 평가의 한계](wiki/05-development/transcript-review.md)를 참고하세요.

품질 평가는 저장된 검수 JSON과 음성으로 [정답 입력 팩과 CER 보고서](wiki/05-development/transcript-quality-evaluation.md)를 만들 수 있습니다. 단어 정보는 [구간별로 검증해 분할](wiki/05-development/word-alignment-recovery.md)하며, 불확실한 구간은 원문과 시간을 유지합니다. 고정 샘플의 표시 가독성 초안은 아직 미달이며 [실제 평가와 통합 기록](wiki/05-development/harness/changes/transcript-quality-integration.md)을 확인하세요.

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
migrations/   # Alembic 환경과 작업·자산·편집 버전 등 DB 스키마 변경 이력
tests/        # unit·process·media·integration 검사와 실행 안내
scripts/      # 검사 진입점·다이어그램 생성
wiki/         # 카테고리별 프로젝트 문서
docs/         # 다이어그램과 이전 문서 링크 안내
.github/      # CI·PR 양식
```

GitHub Actions는 검사와 Docker 빌드를 실행하며 자동 배포·유료 AI 호출을 하지 않습니다. 필수 검사 병합 차단은 별도 저장소 규칙이 필요합니다.

# 구현 현황과 검증 기록

> 상태: 2026-11-15 기준 스냅샷 · 기준일: 2026-11-15 · 유지관리: 프로젝트 개발자

[위키 홈](../README.md) · [카테고리 목차](README.md)

## 현재 상태

VIDEO-003은 웹 입력·작업 상태·새로고침 복구·미리보기·다운로드를 연결한다. [웹 사용·검사 계약](../05-development/web-video-extraction.md)을 기준으로 한다. 아래 VIDEO-002 기록은 당시 API 구현의 근거이며 웹 기능은 별도 검증한다.

VIDEO-002의 CLI·비동기 API는 [PR #1](https://github.com/Juhye0k/short-form/pull/1)로 main에 병합됐다. VIDEO-003은 그 기반 위의 웹 사용자 흐름이다. 실제 AI 추천이나 공개 웹 서비스 운영 완료를 의미하지 않는다. 이전 커밋·게시 근거는 [VIDEO-002 작업 기록](video-002-work-log.md)에 남긴다.

| 항목 | 상태 | 근거 |
|---|---|---|
| FastAPI 생존·준비 점검 | 구현 | [main.py](../../app/main.py) |
| DB 연결·migration 환경 | 구현 | [db.py](../../app/db.py), [migrations](../../migrations) |
| Redis·Celery 진단 | 구현 | [worker.py](../../app/worker.py) |
| Compose·CI·검사 | 구현 | [compose.yaml](../../compose.yaml), [CI](../../.github/workflows/ci.yml) |
| 업무 테이블·API | 로컬 구현 | video_jobs, 접수·조회·다운로드 API |
| 링크 입력·10초 추출 CLI | 로컬 구현 | [실행·계약](../05-development/video-extraction.md), [서비스](../../app/services/video.py) |
| 링크 입력·업무 워커 연결 | 로컬 구현 | 기존 영상 서비스를 Celery에 연결; 웹 업로드 미구현 |
| 실제 AI 분석·추천 | 미구현 | 실험 계획만 존재 |
| 다운로드 API / 웹 화면 / 자막 편집 | API·추출 화면 구현 / 자막 편집 미구현 | VIDEO-003은 지정 구간 추출 흐름 |
| 인증·SNS·운영 배포·자동 복구 | 미구현 | 후속 결정 필요 |
| 카테고리형 프로젝트 위키 | 작성 | [위키 홈](../README.md) |

## 확인된 검증 증거

### VIDEO-003 — 웹 추출 흐름

- 입력·접수·상태·새로고침 복구·미리보기·다운로드를 FastAPI 정적 화면으로 연결했다.
- 기본 검사 86개 통과. 실제 인프라 통합 27개 통과하며 그중 14개는 Chromium 브라우저 검사다.
- 데스크톱 결과 화면과 모바일 390px 입력 화면을 캡처해 확인했다. 일반 실행 이미지와 테스트 이미지의 브라우저 의존성을 분리한다.
- Safari·Firefox·실제 모바일 기기·부하 검사는 미실행이다. 상세 계약·발견 사항은 [웹 추출 기록](../05-development/web-video-extraction.md)을 따른다.

### VIDEO-002 — 비동기 영상 추출

- 시작 커밋 `000fee0`, 작업 브랜치 `feat/video-002-async-extraction`. 아래는 로컬 작업 트리 검사이며 원격 CI 결과가 아니다.
- 게시한 구현 커밋 [32e992c](https://github.com/Juhye0k/short-form/commit/32e992cdefccb9668bcbc2af38499486961da89c)의 [GitHub Actions 43694535440](https://github.com/Juhye0k/short-form/actions/runs/43694535440)에서 checks·integration 모두 성공했다. 아래 로컬 결과와 구분한다.
- `uv run python scripts/verify.py`: Ruff·서식·기본 검사 82개·Alembic 오프라인 SQL 통과, 통합 13개 제외.
- `docker compose -f compose.integration.yaml run --rm runner`: 실제 PostgreSQL·Redis·Celery·FFmpeg 통합 검사 13개 통과. 동시 선점·발행 경쟁·수동 실패/완료 경쟁·재전달·실패·HTTP 다운로드 포함.
- 일반 production 이미지 빌드와 마이그레이션·API·워커 실행 성공. 테스트 워커의 대역 없이 공개 MP4를 시작 5초부터 처리해 출력 10.0초·음성 유지·전체 디코딩·원본 보존을 확인하고 HTTP로 732,218바이트 다운로드했다.
- 샌드박스에서 별도 실행한 DB 검사 1개는 pytest 공용 임시 경로 권한으로 실행되지 못했다. 이후 격리 Linux 컨테이너에서 동일 검사를 포함한 13개 전체 통과를 확인했다. 초기 통합 빌드에서 `.dockerignore`의 tests 제외를 발견하고 테스트 단계에서만 복사하도록 수정했다.
- 기존 Starlette/httpx 경고와 로컬 pytest 캐시 권한 경고는 남아 있다. 실제 워커 강제 종료·hard timeout 실험, 자동 복구, 부하 검사는 수행하지 않았다. soft timeout 처리는 대역 예외로, 중단 후 상태 충돌은 실제 DB로 검사했다.
- [실행 안내](../05-development/async-video-jobs.md), [요구사항·회귀 검사](../05-development/harness/video-002-requirements.md), [기술 결정](../04-decisions/adr-003-redis-celery.md).

### VIDEO-001 — 링크 기반 추출

- 작업 시작 커밋: `b549c6b6088f087420fec225ed0bc6761082a2cc`. 아래는 로컬 커밋 직전 검증 근거이며 원격 CI·Wiki 게시는 별도다.
- `uv run python scripts/verify.py`: Ruff·서식·56개 검사·Alembic 오프라인 검사 통과, 인프라 검사 2개 제외. 기존 Starlette/httpx 사용 중단 예정 경고와 샌드박스의 pytest 캐시 쓰기 권한 경고는 남아 있으며 검사 실패는 아니다. 문서 상대 링크와 `git diff --check`도 확인했다.
- 공개 MP4 `https://media.w3.org/2010/05/sintel/trailer.mp4`: 5초부터 추출, 출력 10.0초, 음성 유지·전체 디코딩·원본 SHA-256 동일 확인.
- 공개 YouTube `aqz-KE-bpKQ`: 5초부터 추출, 출력 10.0초, 같은 검사 통과.
- 사용 도구: FFmpeg/FFprobe 9.0.2, Deno 2.9.8, yt-dlp 2026.10.26. 실제 버전·시간·검사 JSON은 Git 제외 `.artifacts/video-runs`에 보관한다.
- 실패 사례: 첫 MP4 샘플은 HTTP 403, 첫 YouTube 테스트 영상 `BaW_jenozKc`는 unavailable. 실패를 성공으로 처리하지 않고 `DOWNLOAD_FAILED`로 기록했다. 다른 공개 샘플로 성공 경로를 확인했다.
- Docker Desktop Linux 엔진이 실행되지 않아 로컬 PostgreSQL·Redis·Celery 통합 검사와 Docker 빌드는 수행하지 못했다. 기존 통합 CI는 유지한다.
- 하네스에서 발견한 결함과 해결 근거: [시간 초과 후 자식 프로세스가 남는 문제](../05-development/harness/changes/video-001-process-timeout.md). 상세 재현·수정·제한은 해당 기록에서 관리한다.
- 커밋 전 재검증: 기본 56개 검사 통과, 공개 MP4 실행 `49b9c201e66a4c87b2d97a3421a95374`와 YouTube 실행 `39debadee5374a56861c4a6e71b3a2b5` 모두 시작 5초·출력 10.0초·음성 유지·디코딩·원본 보존 검사 통과. 결과 JSON·영상은 로컬 산출물에만 보관한다. Docker 엔진은 계속 미실행 상태여서 실제 인프라 검사와 이미지 빌드는 미실행이다.

### 하네스 파일 구조 정리

제품 코드는 유지하고 검사를 unit·process·media·integration으로 분리했다. [하네스 시작 문서](../05-development/harness/README.md), 요구사항 연결표, 개선 기록 양식을 추가했다. 이전 문서 경로는 새 위치 안내로 유지하며 원격 Wiki에는 아직 게시하지 않았다.

- 이동 전후 수집 항목 58개와 테스트 함수·클래스의 구문 구조가 동일함을 확인했다. 제품 코드·의존성·검사 진입점·CI 설정의 파일 해시도 작업 시작 시점과 동일하다.
- `uv run python scripts/verify.py`: 기본 검사 56개 통과, 인프라 검사 2개 제외; Ruff·서식·Alembic 오프라인 검사 통과. 문서 링크·연결표의 테스트 이름·diff 공백 검사도 통과했다.
- 실제 인프라와 외부 링크 검사는 이번 문서·배치 변경에서 재실행하지 않았다. 원격 CI·Wiki 게시는 미실행이며 기존 Starlette/httpx 및 pytest 캐시 권한 경고는 남아 있다.

### 기존 개발 기반

- 기준 코드 커밋: [2989ee4](https://github.com/Juhye0k/short-form/commit/2989ee45f27b8c26804058b7ce17458cd0d42d48).
- [CI 실행 43672654952](https://github.com/Juhye0k/short-form/actions/runs/43672654952): checks와 integration 성공.
- 기본 검사 6개, 실제 인프라 통합 검사 2개, Alembic 설정·접속, Compose 설정, Docker 빌드 확인.
- 통합 실행은 GitHub Linux 환경의 결과다. 당시 로컬 Docker 엔진이 꺼져 있어 로컬 통합 성공 증거는 없다.

이는 해당 커밋의 증거이며 이후 커밋의 성공을 자동으로 보장하지 않는다. 최신 변경은 해당 커밋 CI를 별도로 확인한다.

## 하네스 개선 이력

첫 CI에서 `uv run pytest`가 app을 찾지 못했다. 기본 검사에서 쓰던 `python -m pytest`와 실행 경로가 달랐기 때문이다. pytest의 pythonpath를 명시해 두 진입점이 같은 루트를 사용하도록 수정했고 재실행으로 확인했다. 테스트를 제거하거나 실패를 무시하지 않았다.

CI 액션 런타임 경고를 정리하고 runner를 Ubuntu 24.04로 고정했다. 현재 잠금 파일은 패키지 버전을 기록하지만 Docker 기본 이미지 태그까지 불변 digest로 고정한 구성은 아니다.

## 다음 작업

다음 범위는 웹 입력·상태 표시·다운로드 연결을 별도 요구사항으로 정한다. 자동 복구·AI·자막·SNS는 이번 구현 범위가 아니다.

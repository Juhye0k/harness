# 검증 계층과 실행 방법

코드를 바꾼 뒤 기본 검사로 오류를 확인하고, DB·큐·영상 흐름을 바꿨다면 실제 인프라와 브라우저까지 검사한다. 검사 통과와 실제 추천·자막 품질은 별도로 판단한다.

> 상태: 현재 검사 + 후속 평가 방향 · 기준일: 2026-11-15 · 유지관리: 프로젝트 개발자

[위키 홈](../../README.md) · [하네스 목차](README.md)

## 검사 범위

| 검사 | 현재 확인하는 것 | 확인하지 않는 것 |
|---|---|---|
| Ruff | 코드 오류 패턴·서식 | 업무 결과의 정확성 |
| tests/unit | 생존/준비 점검·환경 설정·영상 규칙·링크·대역·오류 처리 | 실제 도구·DB·워커·YouTube 접근 가능성 |
| tests/process | 실제 로컬 하위 프로세스 실패·시간 초과·종료 | 실제 영상 처리·원격 서버 |
| 실제 FFmpeg 검사 | 합성 영상의 구간·길이·트랙·원본 보존·결과 저장 | 실제 AI 품질 |
| 통합 검사 | 실제 PostgreSQL·Redis·Celery·FFmpeg, 선점 경쟁, HTTP 다운로드 | 외부 영상 서버·자동 복구 |
| Alembic | 오프라인 SQL·실제 video_jobs 테이블 생성 | 운영 데이터 마이그레이션 |
| Docker 빌드 | 이미지 생성 | 운영 배포·고가용성 |

최신 로컬 실행 결과와 미실행 검사는 [현황 기록](../../07-governance/status.md)에서 확인한다.

## 기본 검사

```powershell
uv sync --locked
uv run python scripts/verify.py
```

첫 실패에서 비정상 종료한다. 기본 검사는 외부 인프라를 사용하지 않고 integration 표시 테스트를 제외한다. FFmpeg·FFprobe는 필수이며, 누락 시 영상 검사를 건너뛰지 않고 실패한다. Windows에서는 준비된 `.tmp/tools` 도구도 자동 검색한다. 일반 `pytest` 실행에서도 RUN_INTEGRATION=1이 아니면 인프라 통합 검사는 건너뛴다. 실제 외부 링크 검사는 [영상 CLI](../video-extraction.md)로 별도 실행한다.

## 검사 선택 실행

검사 파일의 배치와 선택 실행은 [tests 안내](../../../tests/README.md)를 참고한다. `pytest tests/unit`, `pytest tests/process`, `pytest tests/media`로 각각 실행할 수 있다. 전체 수집은 `uv run python -m pytest --collect-only -q`로 확인한다. `integration` 마커와 기본 검사 제외 규칙은 유지한다.

## 실제 워커 통합 검사 — 격리 환경

```powershell
docker compose -f compose.integration.yaml up --build -d api worker analysis-worker sns-worker
docker compose -f compose.integration.yaml run --rm runner
docker compose -f compose.integration.yaml logs --tail=200
docker compose -f compose.integration.yaml down --volumes
```

마지막 명령은 `shortform-integration` 전용 테스트 볼륨만 정리한다. 일반 개발 Compose에 `down --volumes`를 실행하지 않는다. 테스트 환경은 호스트 포트를 열지 않고 개발 DB·Redis·영상 볼륨을 공유하지 않는다.

통합 이미지에는 tests와 개발 의존성을 포함한다. 일반 production 이미지는 포함하지 않는다. 외부 다운로드·AI·YouTube는 합성 대역으로 대체하고 실제 HTTP·DB·Redis·Celery·FFmpeg·다운로드를 검사한다. `RUN_INTEGRATION=1`은 DB/진단, `RUN_VIDEO_INTEGRATION=1`은 이 전용 워커가 필요한 영상 흐름을 활성화한다.

VIDEO-003부터 같은 runner가 Playwright Chromium 브라우저 검사도 실행한다. 테스트 이미지에 Chromium·시스템 라이브러리를 설치하며 production 이미지에는 추가하지 않는다. 실제 영상 흐름과 오류 응답 대역을 분리해 새로고침·중복 제출·통신 오류·미리보기·다운로드를 검증한다.

검증 페이지의 [화면 회귀 검사](../../../tests/integration/test_shorts_verification.py)는 390·768·1440·1920px에서 가로 넘침·카드 겹침과 실제 사용 너비를 확인한다. 전체화면 진입·복귀, 새로고침 시 읽기 전용 조회, 표시 품질 미통과 시 SRT 다운로드 차단도 검사한다. 모바일 한 크기의 넘침 검사만으로는 공통 그리드 스타일 때문에 생기는 데스크톱 카드 겹침을 잡을 수 없었다. 원인과 수정 근거는 [작업 기록](records/2026-11-17-verification-layout.md)을 참고한다.

## CI와 검사 증거

FLOW-001은 [시작부터 끝까지의 브라우저 검사](../../../tests/integration/test_complete_flow.py)를 기존 integration에 포함한다. 실패하면 단계별 trace·화면을 확인하고 제품 수정과 회귀 검사를 같은 작업 기록에 연결한다. 새로고침·중복 클릭·편집 버전·다운로드/전송 파일 일치·사람 확인 전 전송 차단을 검사하며, 실제 인식·추천 품질은 판정하지 않는다. CI 합성 증거 수집과 범위는 [전체 흐름 안내](../complete-flow.md)를 따른다.

GitHub Actions는 checks와 integration 작업을 실행한다. 통합 작업은 일반 이미지 빌드와 격리 Compose 검사를 수행한다. 배포·유료 모델 호출은 없다. 통합 실패 시 Compose 로그를 출력하고 종료 시 테스트 환경을 정리한다.

코드를 바꾸지 않는 문서 변경은 링크·구현 일치 검토가 중심이다. 저장소 지침상 기본 검사는 실행하되 문서 변경을 이유로 새 업무 테스트를 만들지 않는다.

## 실패 검사와 실제 품질 평가

실패 경로는 [FAIL-E2E-001](../failure-path-testing.md)에 따라 분석 request_id receipt·응답 유실 복원·도구 실패·중복 전달 검사를 구현했다. 결정적 실패 검사는 기존 integration에 포함한다. `uv run python scripts/run_failure_drills.py`는 생성한 격리 프로젝트에서만 실제 워커/API 종료를 검사하며 별도 수동 CI로 실행한다. 로컬 실행 결과·실패와 수정은 [통합 기록](records/2026-11-17-main-integration.md)을 따른다. 자동 복구·실제 제공자 장애를 검증하는 기능은 아니다.

2단계는 출력 파일·실패·중복 처리를, 3단계는 사용자 흐름을, 4단계는 고정 영상의 추천 품질·비용을 추가한다. 실제 모델 평가는 일반 CI와 분리한다.

# 한국어 자막 포함 세로 영상 출력 확인 — 2026-11-17-subtitle-render-spike

> 상태: 출력 1단계 기술 검증 완료 / 후속 편집 기능은 미구현 · 기준일: 2026-11-17

[위키 홈](../../../README.md) · [작업 기록 목차](README.md)

## 문제와 완료 기준

- 기록 ID: `2026-11-17-subtitle-render-spike`. 실제 Issue 번호는 없다.
- 목적: 자막 편집 구현에 앞서 현재 FFmpeg 환경에서 한국어 자막·세로 화면·클립 시간 변환을 실제 파일로 확인한다.
- 범위: 외부 입력 없이 합성 영상과 고정 자막으로 실행하는 로컬 CLI, 출력 검사, 회귀 검사와 실행 안내. 편집 UI·DB·업무 워커 연결은 후속이다.
- 완료 기준: 별도 경로에 720×1280 MP4·클립 기준 SRT 생성, 길이 ±0.1초·음성·전체 디코딩·원본 보존 확인, 자막 표시 시점·여백 확인, 기본 검사 실행.

## 시작 상태와 실행 정보

| 항목 | 관측 내용 |
|---|---|
| 시작 커밋 | `0167efd63d57196b34a80f16ab64aa8ce9773ef8` |
| 기존 변경 | 전사·검증 화면·추천 평가·하네스 문서 등의 미커밋 변경 있음. 보존한다. |
| 종료 커밋·PR | 이 파일을 포함하는 Git 이력과 자막 출력 PR 참조 |
| 환경 | Windows FFmpeg 9.0.2·Malgun Gothic / Debian FFmpeg 5.1.9·Noto Sans CJK KR / Python 3.12·uv 0.11.3 프로젝트 |
| 개발 에이전트 모델·사용량·비용·전체 시간 | 알 수 없음 |
| 제품 외부 AI 호출 | 사용하지 않는 구현 범위 |

## 프롬프트와 결과

### P1 — 계획과 실행 요청

- 입력 표기: 현재 대화의 요약. 개인 자료·경로는 포함하지 않았다.
- 사용자 요청: 자막 편집과 최종 출력 계획을 수립하고, FFmpeg와 각 단계의 역할을 설명한 뒤 진행하도록 요청했다.
- 실행 단위: 설명에서 제안한 첫 단계인 합성 샘플의 한국어 자막 포함 세로 MP4 출력 확인.
- 실제 결과: [샘플 실행 CLI](../../../../app/cli/render_sample.py), [서비스](../../../../app/services/portrait_sample.py), [합성 adapter](../../../../app/adapters/portrait.py), [시간·자막 규칙](../../../../app/domain/portrait.py)과 [실행 안내](../../portrait-subtitle-sample.md)를 추가했다.
- 산출물: Git 제외 경로에 12초 합성 원본·원본 2~12초의 10.0초 720×1280 MP4·클립 기준 SRT·두 줄 자막 PNG·도구/폰트/파일 해시 보고서를 생성했다. Windows와 Linux production 이미지에서 모두 성공했다. 실제 발화 대신 시험음을 사용한다.
- 초기 실패: 단위·영상 검사에 같은 파일명을 사용해 pytest 수집 충돌이 발생했다. 영상 검사 파일명을 `test_portrait_render.py`로 구분했다. uv 캐시와 공용 pytest 임시 폴더의 권한 제한은 권한 있는 실행 및 작업별 새 임시 경로로 분리했다. 제품 assertion을 약화하지 않았다.
- 공통 실행 변경: 자막·폰트의 고정 상대 경로를 사용하려고 하위 프로세스 실행기에 선택적 `cwd`를 추가했다. 부모 프로세스의 작업 디렉터리는 바꾸지 않는다.
- 환경 변경: Linux 한글 렌더링을 위해 Docker·기본 CI에 `fonts-noto-cjk`를 추가했다. 새 Python 패키지·모델·서비스는 없고 `uv.lock`은 유지했다.
- 사람 확인과 차이: 에이전트가 Windows·Linux PNG에서 한글 모양·두 줄·화면 안 표시를 확인했다. 사용자의 샘플 직접 검수·제품 디자인 승인은 미확인이다.

## 사람의 판단과 AI의 작업

- 사용자: 자막 편집·최종 출력 방향을 요청하고 단계 설명 후 실행을 지시했다.
- AI: 단계 분리, 첫 샘플의 화면 구성·스타일·폰트 선택과 구현·검사를 수행했다. 720×1280·원본 전체 배치·여백·고정 스타일은 제안에 따른 첫 기술 확인이며 완성 제품 디자인 승인을 뜻하지 않는다.
- 사용자 직접 구현·샘플 검수: 미확인.

## 초기 혼합 작업 폴더의 검증 이력

다음 수치는 다른 작업의 미커밋 변경이 함께 있던 초기 개발 환경의 이력이다. PR에 분리한 변경의 검사 수치는 아래 P2에서 따로 기록한다.

| 검사·측정 | 명령·환경·입력 | 실제 결과 |
|---|---|---|
| 의존성 | `uv sync --locked` | 성공, 잠금 파일 변경 없음 |
| 기본 검사 | `uv run python scripts/verify.py`; `PYTEST_ADDOPTS`에 새 작업 전용 `--basetemp`와 `-p no:cacheprovider` 지정 | Ruff·서식·334개 검사·Alembic 오프라인 SQL 통과, 통합 64개 제외 |
| Linux 출력 회귀 | 네트워크 차단 컨테이너에서 `python -m pytest tests/unit/test_portrait.py tests/media/test_portrait_render.py -q -p no:cacheprovider` | 28개 통과 |
| production 빌드·샘플 | `docker build --target production -t shortform-harness:portrait-production .`; 해당 이미지에서 네트워크 차단 후 `python -m app.cli.render_sample --output-dir /samples/새폴더` | 빌드·샘플 생성 성공, 10.0초·720×1280·7개 기술 검사 모두 참 |
| 실제 인프라 | 전용 Compose 프로젝트 `shortform-portrait-integration`, 전용 검증 이미지; `docker compose ... run --rm runner` | PostgreSQL·Redis·Celery·FFmpeg·Chromium 통합 64개 통과 |
| 갱신된 브라우저 검사 | 최종 고정 이미지로 `python -m pytest tests/integration/test_shorts_verification.py -q -p no:cacheprovider` | 1개 통과. 본 작업 중 다른 작업에서 갱신된 해당 파일을 재검사했다. |
| 눈으로 확인 | Windows·Linux 샘플 PNG | 한글 모양·두 줄·검은 여백과 화면 안 표시 확인 |
| 문서·변경 검토 | 관련 문서 8개의 상대 링크와 `git diff --check` | 상대 링크 177개·공백 검사 통과 |

앱 내용 해시는 기본 검사 기록 기준 `fca45093b5de72baccea51a6a8c1d61529587ae3fd256ecd6fab146d45194401`이다. 초기 검증 이미지와 해시 대조 당시 작업 폴더의 차이는 다른 작업에서 갱신한 통합 검사 파일 하나였으며 앱 파일은 같았다. 이후 최종 이미지에 소스를 다시 고정하고 갱신된 검사를 실행했다. 대조 시점의 호스트·이미지의 `app/`, `tests/`, `scripts/`, `migrations/` 및 `pyproject.toml`, `uv.lock` **128개 파일**의 상대 경로·내용 해시가 `14058253a3c4dc3580036f402f17e4f17947229b1339711bbe14ff9ceff695b7`로 일치했다. 다른 작업의 CSS·평가 도구 등 이후 변경까지 검증한 것으로 확대하지 않는다.

전용 통합 컨테이너·네트워크·테스트 볼륨을 정리했다. 기존 개발 스택은 변경하지 않았다. 기존 Starlette/httpx 사용 중단 예정 경고 1개가 남는다. 로컬 CI 동등 검사와 원격 GitHub CI를 구분하며, 푸시하지 않아 원격 CI는 미실행이다.

- 도구 성공과 사람이 평가하는 자막 품질을 구분한다. 픽셀 검사는 글자의 의미나 실제 발화와의 일치를 판정하지 않는다.
- 편집 저장·UI·비동기 최종 출력·실제 음성 정렬 품질은 이 단계의 완료 범위가 아니다.

## P2 — PR 생성과 main 반영 요청

- 입력 표기: 현재 대화의 요약. 사용자가 이번 작업을 PR로 올려 main에 반영하고, 완료 후 Herdr 스킬로 이 세션·패널을 닫도록 요청했다.
- 범위 분리: 최신 `origin/main`의 `58f44bb`에서 `feat/portrait-subtitle-sample` 브랜치를 만들고 이번 출력의 코드·검사·문서만 옮겼다. 다른 전사·추천·검증 화면·하네스 변경과 기존 index는 보존했다. 합성 영상·SRT·미리보기·원본 로그·로컬 웹 미리보기 파일은 Git에 넣지 않는다.
- 분리 후 기본 검사: `uv sync --locked`, `uv run python scripts/verify.py` 성공. Ruff·서식·기본 **281개**·Alembic 오프라인 SQL 통과, 통합 58개 제외. Windows FFmpeg 경로와 작업별 pytest 임시 경로는 해당 실행 프로세스에만 지정했다.
- 분리 후 Linux 출력·인프라 검사: 네트워크 차단 컨테이너에서 출력 회귀 **28개**, 전용 `shortform-portrait-pr` 환경의 PostgreSQL·Redis·Celery·FFmpeg·Chromium 통합 **58개**가 통과했다. 기존 브라우저·작업 경쟁 검사도 포함한다. 이전 한국어 폰트 설치 환경을 재사용하되 앱·검사·스크립트·migration 디렉터리를 제거한 새 이미지 레이어에 PR 소스만 복사해 다른 미커밋 모듈이 남지 않게 했다. 기본·통합 검사에 기존 Starlette/httpx 사용 중단 예정 경고 1개가 남는다.
- 문서 검사: 분리된 브랜치의 문서 8개·상대 링크 151개 통과.
- 자동 종료 제한: 이 에이전트의 환경에 `HERDR_ENV=1`이 없어, 스킬의 외부 세션 제어 금지 규칙에 따라 Herdr 제어를 실행하지 않았다. main 반영과 별개의 제한이다.
- 원격 검증: PR과 병합 커밋의 실제 GitHub Actions 결과를 게시 시점에 확인한다. 이 문서의 로컬 통과 수치로 원격 CI 성공을 대신하지 않는다.

## 포트폴리오용 요약

- 문제·제약: 편집 기능에 앞서 한국어 자막과 화면 구성의 출력 가능성을 검증해야 한다.
- 사용자 역할: 제품 방향·단계 실행 요청.
- AI 작업·결과: 고정 합성 입력으로 한국어 자막·클립 시간 변환·세로 배치·음성 유지·원본 보존을 실제 출력과 회귀 검사로 연결했다. 기본 334개·Linux 출력 28개·인프라 통합 64개 및 갱신된 브라우저 검사 1개가 통과했다.
- 성능 개선률·사용자 품질 판정: 측정하지 않았다.

## 게시 상태

- 코드·기록의 게시 상태: 이 파일을 포함한 Git 이력과 자막 출력 PR에서 확인한다.
- GitHub Wiki: 미게시.

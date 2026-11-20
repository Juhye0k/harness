# 링크에서 10초 영상 추출 — 실행과 하네스

> 공개 링크에서 지정한 10초 구간을 원본을 보존하며 추출합니다. CLI 실행, 입력 제한, FFmpeg 검사와 실패 코드를 읽는 방법을 안내합니다.


## 이번에 해결하는 문제

AI 추천에 앞서 영상 입력·추출·검사의 결과를 신뢰할 수 있어야 한다. 첫 구현은 공개 YouTube 단일 영상 또는 MP4 직접 링크와 시작 시간을 받아 10초 MP4를 출력한다. 시작 시각을 알고 있다면 DB 없이 이 명령으로 추출할 수 있다. 후보 추천과 편집은 [제작실](complete-flow.md)에서 진행한다.

## 준비와 실행

Python 3.12와 uv 외에 FFmpeg·FFprobe 실행 파일이 필요하다. YouTube는 Deno도 필요하다. Python 패키지는 `uv sync --locked`로 설치하며 `yt-dlp[default]`에 포함된 EJS를 사용한다. 실행 중 원격 EJS 컴포넌트를 자동 다운로드하지 않는다.

- Windows: [FFmpeg 다운로드 안내](https://ffmpeg.org/download.html)의 Windows 빌드에서 FFmpeg·FFprobe를 준비하고 [Deno 설치 안내](https://docs.deno.com/runtime/getting_started/installation/)에 따라 Deno를 설치한다. 실행 파일의 폴더를 PATH에 추가한다.
- Windows에서는 PATH를 먼저 검색하고, 없으면 `.tmp/tools/ffmpeg/<빌드 폴더>/bin/ffmpeg.exe`·`ffprobe.exe`와 `.tmp/tools/deno/deno.exe`를 찾는다. FFmpeg 빌드 폴더가 여러 개면 임의 선택하지 않고 PATH 설정을 요구한다. 이 작업 공간에는 준비되어 있으나 새로 복제하면 `.tmp/tools`가 없으므로 별도 설치해야 한다. 시스템 PATH·PowerShell 실행 정책은 바꾸지 않는다.
- Ubuntu: FFmpeg 패키지를 설치한다. 일반 CI는 YouTube에 접속하지 않으므로 Deno가 필요 없다.
- `ffmpeg -version`, `ffprobe -version`, `deno --version`으로 확인한다. 도구가 없으면 `TOOL_MISSING`으로 실패하며 검사에서 자동으로 건너뛰지 않는다.

저장소 루트에서 실행한다.

```powershell
uv sync --locked
uv run python -m app.cli.extract_clip --url "https://media.w3.org/2010/05/sintel/trailer.mp4" --start 5
uv run python -m app.cli.extract_clip --url "https://www.youtube.com/watch?v=aqz-KE-bpKQ" --start 5
uv run python scripts/verify.py
```

링크의 쿼리에 `&` 등이 있으므로 URL 전체를 따옴표로 감싼다. `--start`는 초 단위 소수이며 URL의 `t` 값보다 명시한 시작 시간이 기준이다. 성공 종료 코드는 0, 실패는 1이다. 잘못된 CLI 인자는 stderr에 JSON으로 알리고, 정상 파싱된 실행의 결과는 stdout과 결과 파일에 기록한다. 저장소에 쓸 권한이 없으면 결과 파일 대신 stderr/stdout 오류만 남을 수 있다.

## 모듈 연결

```text
app.cli.extract_clip                 입력 파싱·종료 코드
  → app.services.video.execute       순서 제어·실행 폴더·결과 기록
    → adapters.fetch_worker          별도 다운로드 프로세스
      → yt-dlp 또는 adapters.download
    → adapters.media                 FFprobe → FFmpeg → FFprobe → 전체 디코딩
      → domain.video                 구간·길이·트랙 판정
    → 검증된 파일 확정·result.json
```

`adapters.process`는 인자 배열 실행, 시간 제한, 하위 프로세스 종료와 다운로드 작업 공간 크기 검사를 담당한다. Windows에서는 psutil로 자식부터 종료하고 종료 여부를 확인하며, Linux에서는 독립 프로세스 그룹에 종료 신호를 보낸다. [psutil 공식 안내](https://psutil.readthedocs.io/stable/index.html)를 참고한다. Celery 워커와는 별개인 **로컬 하위 프로세스**다. PostgreSQL·Redis·Celery 없이 동작하고 추후 워커가 같은 서비스를 호출할 수 있다.

하네스는 이 서비스와 구분한다. **AGENTS.md → 위 계약 → tests → scripts/verify.py → CI → 실패 회귀 검사**가 개발 하네스다. 테스트 실패를 고치는 주체는 개발자 또는 코딩 에이전트이며, 자동 수정 에이전트는 구현하지 않았다.

## 입력·출력 계약

| 항목 | 현재 규칙 |
|---|---|
| 출처 | 공개 YouTube 단일 영상·HTTP(S) MP4 직접 링크 |
| 제외 | 재생목록·라이브·로그인/쿠키 필요 영상·기타 사이트 페이지 |
| 시작점 | 0 이상의 유한한 초 단위 숫자 |
| 구간 | 시작 + 10초가 원본 영상 트랙 길이를 넘으면 거부 |
| 자원 | 원본 20분 이하, 다운로드 500MiB 이하, YouTube 최대 720p 선택 |
| 시간 | 다운로드 전체 300초, 소켓 대기 15초, 추출 120초, 개별 검사 30초 |
| 길이 | 출력 영상 트랙과 컨테이너 길이 모두 10초 ±0.1초 |
| 트랙 | 첫 영상 트랙, 원본에 음성이 있으면 첫 음성 트랙 유지; 무음 영상 허용 |
| 형식 | H.264·yuv420p 영상, 음성이 있으면 AAC, MP4; 세로 크롭은 하지 않음 |
| 원본 | 별도 경로 보존·처리 전후 SHA-256 비교·기존 파일 덮어쓰기 거부 |
| 공개 | 모든 검사 통과 후에만 최종 출력 경로 생성 |

직접 다운로드는 목적지의 공개 IP를 확인하고 해당 IP에 연결한다. 리디렉션에서도 같은 검사를 반복하며 프록시 환경 변수로 우회하지 않는다. 포트는 HTTP/HTTPS 기본 포트 범위만 허용한다. FFmpeg에는 로컬 MP4/WebM 컨테이너만 전달하고 외부 네트워크 프로토콜을 허용하지 않는다.

YouTube는 영상·음성 합산 다운로드량과 병합 중 작업 공간도 제한한다. 병합 전후 파일이 동시에 존재하면 실제 완성 파일이 500MiB 미만이어도 제한에 걸릴 수 있다. 도구 단계별 제한이며 실행 전체를 300초로 보장하는 뜻은 아니다.

```text
.artifacts/video-runs/<실행 ID>/
  source/       다운로드 원본; 실패한 다운로드의 부분 파일도 남을 수 있음
  work/         임시 출력; 성공·실패 시 해당 출력 정리
  output/       검사 통과한 clip.mp4
  result.json   실행 단계·오류·길이·트랙·검사·원본 해시·도구 버전·시간
```

결과 확정에는 같은 파일시스템의 하드 링크를 사용해 기존 경로를 교체하지 않는다. 로컬 NTFS/Linux 파일시스템을 대상으로 하며 이를 지원하지 않는 저장장치에서는 `IO_FAILED`로 실패한다. 원본·결과는 자동 만료하지 않으며 디스크 사용량을 확인해 사용자가 정리한다. `.artifacts`와 `.tmp`는 Git에서 제외된다. URL·쿼리·도구 원본 로그는 결과 JSON에 기록하지 않는다. 결과에는 로컬 경로가 있으므로 공개 공유 전 제거한다.

## 오류 읽기

| 코드 | 의미 |
|---|---|
| INVALID_INPUT | URL·시작 시간·접속 대상 또는 지원 범위 오류 |
| DOWNLOAD_FAILED | HTTP 오류·영상 접근 제한·다운로드 불완전 |
| LIMIT_EXCEEDED | 원본 길이·다운로드량·작업 공간 제한 초과 |
| INVALID_MEDIA | 지원 컨테이너 아님·손상·영상 트랙/길이 확인 불가 |
| INVALID_RANGE | 요청 구간이 원본 범위를 넘음 |
| TOOL_MISSING / TOOL_FAILED | 실행 도구 누락 / 비정상 종료 |
| TIMEOUT | 다운로드·도구 제한 시간 초과 |
| TERMINATION_FAILED | 시간 초과 등으로 중단을 시도했으나 프로세스 종료 확인 실패 |
| OUTPUT_INVALID | 출력 길이·트랙·원본 보존 검사 실패 |
| OUTPUT_CONFLICT / IO_FAILED | 기존 경로 충돌 / 파일 접근·저장 실패 |

`stage`와 `error.code`를 함께 본다. 실패한 작업을 자동 재시도하지 않는다. YouTube 접근 제한을 로그인·쿠키로 우회하지 않으며, 공개 영상도 공급자 변경·지역·요청 제한에 따라 실패할 수 있다.

## 검증과 기록

기본 검사는 외부 영상에 접속하지 않는다. 테스트가 빨강 10초 + 파랑 10초와 음성 신호를 생성하고, 7.5초부터 추출한 영상의 색상 전환이 클립 2.5초 지점에 나타나는지 확인한다. 길이·트랙·무음·원본 해시·오류·시간 초과·하위 프로세스 종료·주소 차단·다운로드 한도를 함께 검사한다. 실제 YouTube는 downloader 대역으로 계약을 검사하고 수동 외부 실행을 별도로 기록한다.

VIDEO-001은 사용자 요청과 승인된 계획을 기준으로 구현했다. 원본 프롬프트/비공개 내부 추론은 저장하지 않는다. 도구 버전과 처리 시간은 실행 결과에서 관측한 값이며 모델 비용은 수집하지 않았다. 공개 샘플 실행 증거와 미실행 인프라 검사는 [현황 기록](../07-governance/status.md)에 남긴다. 로컬 커밋과 원격 CI·Wiki 게시 여부는 구분한다.

<details>
<summary>작성 시점과 상태 이력</summary>

> 상태: 로컬 CLI 구현 · 작업 ID: VIDEO-001 · 기준일: 2026-11-15 · 유지관리: 프로젝트 개발자

</details>

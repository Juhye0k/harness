# 신입 개발자 시작 안내

> 처음 참여한 개발자가 코드를 실행하고 정상 상태를 확인하기 위한 안내입니다. 필요한 도구, 실행 순서, API를 수정하는 방법과 종료·장애 확인 경로를 제공합니다.

먼저 개발 환경을 실행하고 상태 API를 확인한 뒤, 실제 워커 통합 검사로 연결을 확인한다. 아래 절차를 마치면 시스템을 켜고 끄는 방법과 기능 수정 전 읽을 문서를 알 수 있다.


[위키 홈](../README.md) · [카테고리 목차](README.md)

## 첫날 읽을 순서

1. [문제 정의](../01-product/problem-definition.md): 무엇을 해결하는가?
2. [현황](../07-governance/status.md): 현재 어디까지 구현했는가?
3. [시스템 구조](../03-architecture/system-overview.md): 어떤 프로세스가 무엇을 맡는가?
4. [실행 흐름](../03-architecture/runtime-flows.md): 요청은 어디로 이동하는가?
5. 아래 실행 절차를 수행하고 [하네스](harness/workflow.md)를 읽는다.

## 준비 사항

Git, uv, Python 3.12, Docker Desktop Linux 엔진을 준비한다. 설치된 패키지 버전은 uv.lock을 따른다. 아래 명령은 저장소 루트에서 실행한다. Windows는 PowerShell 기준이며 워커는 Linux 컨테이너를 사용한다.

```powershell
git clone https://github.com/Juhye0k/short-form.git harness
cd harness
uv sync --locked
uv run python scripts/verify.py
```

## 전체 구성 실행

```powershell
docker compose up --build -d
docker compose ps
curl.exe http://localhost:8000/health/live
curl.exe http://localhost:8000/health/ready
```

두 상태 API가 200을 반환하는지 확인한다. 문서는 http://localhost:8000/docs 에서 볼 수 있다. 이것만으로 워커 동작이 검증되는 것은 아니다. [통합 검사](harness/verification.md)를 추가로 확인한다.

## API를 직접 수정하며 실행

전체 구성을 이미 켰다면 `docker compose stop api`로 8000 포트를 비운다. `.env`가 없을 때만 예시를 복사하고 기존 설정을 덮어쓰지 않는다.

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose up -d postgres redis
uv run uvicorn app.main:app --reload
```

호스트에서 실행하는 API는 localhost, Compose 내부 프로세스는 postgres·redis 서비스 이름을 사용한다. Compose의 URL은 파일에서 직접 설정하므로 로컬 .env 변경이 컨테이너 설정까지 자동 반영되지는 않는다.

## 종료와 문제 확인

`docker compose logs --tail=100 api worker`로 확인하고 `docker compose down`으로 종료한다. down은 이름 있는 데이터 볼륨을 유지한다. `down -v`는 데이터를 지우므로 일상 종료 명령으로 사용하지 않는다.

포트 충돌·Docker 엔진 중단·연결 실패는 [운영 점검](../06-operations/runbook.md)을 참고한다. 초기 기본 암호는 로컬 개발용이며 이 설정을 인터넷에 노출하지 않는다.

<details>
<summary>작성 시점과 상태 이력</summary>

> 상태: 현재 실행 절차 · 기준일: 2026-11-15 · 유지관리: 프로젝트 개발자

</details>

# 비동기 10초 추출 실행 — VIDEO-002

> 영상 처리가 끝날 때까지 HTTP 요청을 열어 두지 않고 작업 번호로 결과를 조회합니다. 비동기 추출 실행 방법과 강제 종료된 작업의 수동 처리 조건을 설명합니다.

[위키 홈](../README.md) · [개발 목차](README.md)


## 범위

영상 URL과 시작 시간을 등록하면 작업 번호를 즉시 받는다. 워커가 기존 VIDEO-001 서비스를 호출하고, 사용자는 상태를 조회한 후 검증된 MP4를 내려받는다. AI 추천·자막 편집·SNS·인증·자동 재시도는 포함하지 않는다. 코드 기준은 `feat/video-002-async-extraction`이며 main 병합·운영 배포와 구분한다. [작업 기록](../07-governance/video-002-work-log.md)에서 게시·검증 근거를 확인한다.

## 실행

Docker Desktop의 Linux 엔진을 실행하고 저장소 루트에서 다음 명령을 사용한다. 마이그레이션이 성공한 뒤 API와 워커가 시작한다. FFmpeg·FFprobe·Deno는 이미지에 포함된다.

```powershell
docker compose up --build -d
$body = @{url='https://media.w3.org/2010/05/sintel/trailer.mp4'; start_seconds=5} | ConvertTo-Json
$job = Invoke-RestMethod -Method Post -Uri 'http://localhost:8000/jobs/video-extractions' -ContentType 'application/json' -Body $body
Invoke-RestMethod "http://localhost:8000/jobs/$($job.job_id)"
```

조회 결과가 `succeeded`이면 다운로드한다. `failed`이면 오류 코드를 먼저 확인한다. 대기 중에는 다운로드가 409를 반환한다.

```powershell
Invoke-WebRequest "http://localhost:8000/jobs/$($job.job_id)/download" -OutFile "$($job.job_id).mp4"
```

출력은 Docker `video_data` 볼륨의 `/data/jobs/<job_id>/<run_id>/output/clip.mp4`다. 워커는 쓰기, API는 읽기 전용으로 연결한다. API는 경로 대신 다운로드 주소를 반환한다. 기존 로컬 CLI는 DB·Redis 없이 계속 사용할 수 있다.

## 강제 종료된 작업 처리

일반 처리 오류와 소프트 시간 초과는 워커가 실패를 저장한다. 워커 전체 종료·하드 시간 초과·DB 완료 기록 실패는 `running`을 남길 수 있고, 발행 중 API 종료는 `pending`을 남길 수 있다. 이를 감지하는 감시 프로세스는 없다. 오래됐다는 이유만으로 실패 처리하지 않는다.

1. `docker compose logs worker api`와 작업 상태를 확인한다.
2. 해당 작업을 실행할 수 있는 API·워커를 멈추고 실행 중인 프로세스가 없는지 확인한다. 현재 단일 호스트에서는 `docker compose stop api worker`를 사용한다. 다른 호스트의 워커가 있다면 그쪽도 확인해야 한다.
3. 아래 명령에 실제 작업 UUID와 확인 사유를 넣는다.

```powershell
docker compose run --rm --no-deps worker /app/.venv/bin/python -m app.cli.fail_job JOB_UUID --confirmed-stopped --reason "API와 워커 종료 확인 후 중단 처리"
docker compose up -d api worker
```

명령은 `pending` 또는 `running`에만 적용되며 사유를 DB에 보관한다. 이미 완료된 상태는 바꾸지 않는다. `--confirmed-stopped`는 관리자의 확인 표시이며 프로세스 중단을 자동 증명하지 않는다. `queued`는 아직 전달 가능한 메시지가 있으므로 이 명령에서 제외한다. 필요하면 기존 작업을 조사한 후 새 요청을 보낸다. 같은 작업 ID를 자동 재사용하지 않는다.

## 확장 전 조건

현재는 localhost 전용이고 인증·요청 제한·소유권 검사·출력 정리가 없다. 외부 공개 전 이를 추가해야 한다. 다중 호스트에서는 공유 파일 볼륨을 객체 저장소로 바꾸고, 중단 자동 복구 전에는 outbox·lease·attempt ID와 오래된 실행의 부작용 차단을 설계한다. [선택 근거](../04-decisions/adr-003-redis-celery.md)와 [상태 계약](../03-architecture/data-and-jobs.md)을 먼저 읽는다.

<details>
<summary>작성 시점과 상태 이력</summary>

> 상태: 로컬 기능 브랜치 구현 · 기준일: 2026-11-15 · 유지관리: 프로젝트 개발자

</details>

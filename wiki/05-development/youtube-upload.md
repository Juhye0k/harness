# YouTube 계정 연결과 확인 후 업로드 — SNS-006

> 확인한 출력 영상을 연결한 YouTube 채널에 한 번 전송합니다. 계정 연결·승인·비공개 기본값과 결과가 불확실할 때 재전송 대신 세션을 조회하는 절차를 안내합니다.

[위키 홈](../README.md) · [개발 목차](README.md)


## 범위와 사용자 흐름

6단계의 첫 제공자는 YouTube다. 성공한 영상 작업에서 **YouTube에 업로드하기**를 누르거나 `/sns`에서 작업 번호를 입력한다. Google OAuth는 사용자가 비밀번호를 앱에 전달하지 않고 업로드 권한을 허용하는 절차다. 연결한 채널과 출력 영상·제목·공개 범위·아동용 여부를 먼저 확인하며, 별도의 동의 체크와 최종 버튼을 눌러야 전송한다. 기본 공개 범위는 비공개다.

기본은 localhost 개발 기능이다. Google 로그인 활성화 시 계정별 자료 소유권도 검사한다. [인증 설정](user-auth-data.md)은 YouTube 전송 권한과 별도로 관리한다. SNS 계정과 업로드는 HttpOnly 브라우저 세션 쿠키에 속하고, 다른 세션은 조회·확인·연결 해제를 할 수 없다. 인증을 끈 개발 모드의 기존 자료는 legacy 정책을 따른다. 운영 HTTPS·백업·비용 제한을 확인하기 전 외부 사용자에게 공개하지 않는다. 쿠키를 지우면 기존 연결·업로드에 접근할 수 없으며, 다시 연결한 새 로컬 계정 기록과 이전 기록 사이의 중복은 막지 못한다.

## 설정과 실행

1. Google Cloud에서 YouTube Data API v3를 켜고 OAuth 동의 화면을 설정한다. 개발용 테스트 사용자와 **웹 애플리케이션** OAuth 클라이언트를 준비한다. 연결할 Google 계정에는 YouTube 채널이 있어야 한다. Google 로그인만 가능한 계정은 YouTube에서 채널을 먼저 만든 뒤 다시 연결한다. 채널 조회 실패 안내는 계정 목록이 비어 있어도 화면에 유지된다.
2. 승인된 리디렉션 URI를 `http://localhost:8000/sns/youtube/callback`으로 등록한다. 앱을 여는 주소와 `SNS_ORIGIN`을 정확히 맞춘다. `localhost`와 `127.0.0.1`은 별도 주소다.
3. 환경 변수로 `ENABLE_SNS_UPLOAD=true`, `SNS_ORIGIN`, `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `SNS_TOKEN_KEY`를 주입한다. 기본은 비활성화다. 테스트용 자격 증명을 실제 설정에 사용하지 않는다.
4. 암호화 키는 `uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`로 생성해 비공개 비밀 저장소에 보관한다. 생성한 값과 토큰을 Git·로그에 남기지 않는다. API와 SNS 워커가 같은 키를 사용해야 하며, 키를 잃으면 다시 연결해야 한다. 키 교체·재암호화 도구는 없다.
5. 실행 전에 `uv sync --locked`, `uv run alembic upgrade head`를 수행한다. Compose를 사용하면 migration 서비스가 처리한다. `docker compose --profile sns up --build -d api worker sns-worker`로 실행한다. 이 명령은 개발 환경을 갱신하므로 병렬 작업 중인 스택에는 실행하지 않는다.

API는 `youtube.upload`와 계정 확인용 `youtube.readonly` 권한을 요청한다. OAuth state는 세션·10분 만료·1회 사용 조건을 가지며 PKCE 검증값을 함께 사용한다. 브라우저에는 토큰을 보내지 않고, DB의 refresh token·PKCE 검증값·업로드 세션 주소를 Fernet으로 암호화한다. 새 의존성 `cryptography`는 이 암호화를 위해 추가했으며 잠금 파일에 반영했다. 자체 OAuth HTTP 처리는 기존 `httpx`를 사용한다.

## 확인·버전·중복 계약

- 초안 생성은 전송하지 않는다. 서버는 성공한 출력의 SHA-256(파일 내용의 해시)을 계산해 출력 버전으로 고정한다. 최대 256MiB 출력만 받는다.
- 최종 확인은 계정 ID·연결 버전·영상 작업 ID·출력 버전·제목·공개 범위·아동용 여부와 `confirmed=true`를 모두 보낸다. 서버 저장값과 다르거나 초안이 15분을 넘거나 연결이 바뀌면 거부한다.
- 확인 시 출력 해시를 다시 검사한다. 워커는 파일의 별도 임시 사본을 만들고 같은 해시를 검증한 뒤 그 사본을 전송한다. 원본과 영상 출력을 수정하지 않는다.
- 초안 요청 번호는 브라우저가 재사용하며 내용이 바뀐 같은 번호는 거부한다. 확인은 계정 행 잠금과 `(계정, 영상 작업, 출력 버전)`의 확인된 업로드 고유 제약으로 직렬화한다. 같은 내용의 반복 확인은 기존 ID를 반환하고, 같은 출력의 제목·공개 범위를 바꾼 요청은 중복으로 거부한다. 실패·미확정 작업도 새 전송으로 바꾸지 않는다.
- 새로고침은 조회만 한다. 브라우저 조회 통신 오류를 처리 실패로 표시하지 않는다. 확인 응답을 잃으면 초안 주소에서 기존 작업을 조회한다.

## 작업 상태와 미확정 처리

`draft → queued → running → succeeded / failed / unknown`이다. PostgreSQL에 상태와 승인값을 보관하고 Redis에는 UUID만 발행한다. queued 작업을 한 번 선점하며 조기 ACK·자동 재시도 없음 계약을 따른다. SNS 전용 큐와 워커를 사용한다.

전송 전 오류와 명확한 제공자 거절은 failed다. 전송 중 timeout·5xx·부분 전송·잘못된 성공 응답 등으로 성공 여부가 불명확하면 unknown이다. 재개 가능한 세션 주소를 미디어 전송 전에 암호화해 저장한다. **재전송 없이 YouTube 상태 확인**은 기존 세션에 빈 상태 조회 요청만 보내며, 성공한 영상 ID를 확인하면 succeeded로 바꾼다. 만료·부분 완료·조회 실패는 unknown을 유지한다. 새 세션 생성·미디어 재전송·자동 재시도는 하지 않는다. YouTube Studio에서도 직접 확인한다.

프로세스 강제 종료·DB 완료 기록 실패는 running을 남길 수 있다. 자동 중단 감지·복구는 없다. 해당 워커가 실제로 멈췄음을 확인한 뒤 `uv run python -m app.cli.mark_upload_unknown UPLOAD_UUID --worker-stopped`로 unknown으로 기록한다. 이미 unknown인 상태를 늦은 워커 완료가 덮어쓰지 못한다. 세션 주소를 저장하기 전에 중단됐다면 앱에서 원격 결과를 확인할 수 없다. 작업 ID와 YouTube Studio를 대조하고 DB를 임의로 queued로 되돌리지 않는다.

연결 해제는 로컬 토큰을 삭제하고 이후 전송·승인을 차단한다. 이미 진행 중인 원격 전송을 취소하거나 Google의 앱 동의를 철회하지 않는다. Google 계정의 연결된 앱 설정에서 동의를 별도로 철회할 수 있다. 예약 게시·삭제·공개 범위 변경·수동 재전송·멀티 플랫폼·Shorts 판정 보장은 구현하지 않았다. 업로드 성공은 YouTube 인코딩·정책 검사·실제 공개 완료와 구분한다.

## 검사와 한계

일반 검사에서는 HTTP 대역으로 OAuth·refresh·비공개 인자·세션 주소 제한·전송 실패를 검사한다. 실제 PostgreSQL에서는 확인·발행·선점 경쟁, 만료·다른 브라우저·변경된 승인, 늦은 완료 차단을 검사한다. 격리 Compose는 테스트 전용 API와 제공자 대역을 사용해 실제 HTTP·Celery·영상 추출·Chromium을 검사한다. production 이미지에는 이 진입점이 포함되지 않는다.

병렬 환경에서는 고유한 프로젝트와 이미지 이름을 지정한다.

```powershell
$env:INTEGRATION_IMAGE='shortform-harness:sns-local-integration'
docker compose -p shortform-sns-local -f compose.integration.yaml up --build -d api worker analysis-worker sns-worker
docker compose -p shortform-sns-local -f compose.integration.yaml run --rm runner
docker compose -p shortform-sns-local -f compose.integration.yaml down --volumes
```

이 테스트 프로젝트만 정리한다.

호스트 포트를 열거나 개발 DB·Redis·영상 볼륨을 공유하지 않는다.

[검사 연결·작업 기록](harness/changes/sns-006-upload.md)에서 실제 실행 결과를 확인한다.

실제 Google 동의와 채널 연결은 별도 승인된 로컬 테스트에서 확인했다.

토큰 만료 및 철회·계정별 업로드 한도·YouTube 처리 품질은 미검증이다.

승인된 가로 합성 영상 1건의 일반 업로드와 세로 합성 영상 1건의 비공개 Shorts 업로드를 확인했다.

세로 파일은 720×1280·10.000초이며 YouTube 처리 완료와 Studio Shorts 탭 분류를 확인했다.

실제 계정·출력 버전·제목·공개 범위의 별도 명시적 승인 전에는 실제 요청을 실행하지 않는다.

## Shorts 출력 확인

[YouTube 공식 기준](https://support.google.com/youtube/answer/15424877?hl=ko)은 정사각형 또는 세로 비율이고 길이가 3분 이내인 새 업로드를 Shorts로 분류한다. 길이가 짧은 가로 영상을 Shorts로 설명하지 않는다. Shorts 테스트 전에는 실제 출력의 영상 트랙 폭·높이, 픽셀 비율, 길이·음성·디코딩·해시를 확인하고 Studio의 Shorts 탭에서 실제 분류 결과를 확인한다.

현재 추출기는 원본 화면 비율을 보존하며 가로 영상을 자동으로 9:16으로 바꾸는 제품 기능은 없다. 이번 실제 Shorts 테스트는 별도 720×1280 세로 합성 출력을 준비해 사용자 승인 후 비공개로 업로드하고 Studio Shorts 탭에서 실제 분류를 확인했다. 출력이 바뀌면 새 해시에 대한 승인을 받고 새 작업으로 전송하며, 이미 올린 영상의 로컬 파일을 덮어쓰지 않는다.

## 공식 문서 확인

2026-11-16에 아래 공식 문서를 확인했다. API의 기본 공개 범위에 기대지 않고 앱이 `privacyStatus=private`를 명시한다. 현재 공식 변경 이력은 미검증 API 프로젝트의 과거 비공개 강제 정책이 해제됐다고 명시하므로, 과거 제한을 안전장치로 가정하지 않는다. OAuth 앱 검증·개별 채널 제한과는 구분한다.

- [웹 서버 OAuth](https://developers.google.com/identity/protocols/oauth2/web-server)
- [YouTube 인증·권한](https://developers.google.com/youtube/data/guides/authentication)
- [계정 채널 조회](https://developers.google.com/youtube/data/reference/rest/v3/channels/list)
- [영상 업로드](https://developers.google.com/youtube/data/reference/rest/v3/videos/insert)
- [재개 가능한 업로드와 상태 조회](https://developers.google.com/youtube/data/guides/using_resumable_upload_protocol)
- [YouTube API 변경 이력](https://developers.google.com/youtube/data/revision_history)

<details>
<summary>작성 시점과 상태 이력</summary>

> 상태: 로컬 구현 · 실제 비공개 Shorts 업로드·Studio 분류 확인 · 기준일: 2026-11-16 · 유지관리: 프로젝트 개발자

</details>

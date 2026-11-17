# 로컬 영상 파일 업로드 — UPLOAD-001

> 상태: 로컬 구현·합성 입력 검증 완료 · 기준일: 2026-11-17

[위키 홈](../README.md) · [개발 목차](README.md)

## 사용자 흐름

10초 추출 화면과 전사·추천 화면에서 파일을 선택하고 ‘선택한 파일 업로드’를 누른다. 실제 전송률과 워커 검증 상태를 표시하며, 원본 검증 완료 후에만 추출·분석을 실행한다. 새로고침은 URL에 저장한 업로드 번호를 조회할 뿐 파일을 다시 보내지 않는다. 연결이 끊기면 먼저 상태를 조회한다. 재개 업로드·자동 재전송은 지원하지 않는다.

한 파일은 최대 **500MiB·20분**이다. MP4/MOV·WebM/Matroska 계열의 실제 헤더·영상 트랙·유한한 길이를 FFprobe로 확인하며 확장자나 MIME만으로 통과시키지 않는다. 원본 전체 디코딩은 업로드 검사의 범위가 아니며, 추출 결과는 기존 길이·트랙·디코딩·원본 보존 검사를 유지한다. 무음 영상은 추출에서 허용하고 음성이 필요한 분석은 기존 규칙을 따른다.

업로드·검증은 외부 AI를 호출하지 않는다. 검증된 원본을 이후 분석에 사용하면 기존 제공자·비용·데이터 전송 설정이 적용된다.

## API와 상태

| 요청 | 동작 |
|---|---|
| POST `/assets/uploads` | `{size_bytes}`로 업로드 생성. 201과 asset_id·upload_url·status_url |
| PUT `/assets/{id}/content` | 파일 바이트 직접 전송. 202 접수 후 비동기 검증 |
| GET `/assets/{id}/upload` | created·receiving·queued·validating·ready·failed, 크기·오류 코드 |
| POST `/jobs/video-extractions` | url 또는 ready인 asset_id 중 하나와 start_seconds로 10초 추출 |
| POST `/analyses` | 기존 asset_id 계약으로 업로드 원본을 전사·추천에 재사용 |

초기 크기는 0 초과·500MiB 이하 정수다. Content-Length가 있으면 선언 크기와 일치해야 하며 없어도 실제 바이트를 제한한다. PUT MIME은 application/octet-stream 또는 video/mp4·video/webm·video/quicktime이다. 전송 시간은 최대 10분이다. 크기 불일치는 400/413, MIME 오류는 415, 중복 수신은 409다. worker 발행 실패는 조회 가능한 failed/DISPATCH_FAILED로 남긴다. 자동 재시도는 없다.

일반 JSON 요청의 64KiB 제한은 유지하고 정확한 파일 PUT 경로만 스트리밍한다. 사용자 파일명·로컬 경로는 저장하지 않는다. UUID 하위 고정 파일명, 수신 크기·서버 SHA-256·상태만 기록한다. Redis에는 원본 ID·작업 ID만 전달하고 영상 바이트는 넣지 않는다.

## 저장·권한·삭제

`UPLOAD_DATA_DIR` 기본값은 `.artifacts/uploads`다. API는 수신 저장소에만 쓰고 기존 원본 볼륨은 읽기 전용으로 유지한다. Compose는 별도의 upload_data/test_upload 볼륨을 API·영상 worker·cleanup에 연결한다. Docker 이미지에서 appuser가 해당 수신 경로에 쓸 수 있게 준비한다.

worker는 수신 파일 크기·해시·형식·20분 제한을 확인한 뒤 관리 원본 폴더에 별도 복사하고 해시를 재검사해 ready로 확정한다. 기존 파일을 덮어쓰지 않는다. 기존 video 큐·조기 ACK·자동 재시도 없음 계약을 사용하며 중복 메시지는 다시 검증하지 않는다.

인증 모드에서 소유권·세션·CSRF와 7일 기한을 유지한다. 타인의 업로드 조회·전송·재사용을 차단한다. 사용 중 자료의 삭제는 보류하고 원본 삭제·탈퇴·만료 시 수신 폴더와 receipt도 정리한다. 만료·탈퇴한 created/queued 업로드는 실행하지 않고 종결한다. 강제 중단된 receiving/validating과 사용 기록은 실제 프로세스 종료 확인 후 수동 처리한다. 기존 무인증 개발 자료는 legacy 정책을 유지한다.

## 검사와 한계

단위 검사: 크기·해시 불일치·20분 초과 시 원본 미공개와 보존. 실제 DB 검사: 64KiB 초과 스트리밍·청크 크기 제한·중복·타인 접근. 실제 Chromium·Celery·FFmpeg: 파일 선택→전송→검증→새로고침 무재전송→10초 추출→저장 원본 전사 재사용.

입력은 생성한 합성 영상이며 실제 AI·SNS를 호출하지 않는다. 사용자별 총 저장량·일별 한도, 최대 크기 실제 부하, 재개 업로드·객체 저장소는 후속 범위다. 검사 결과와 제한은 [작업 기록](harness/records/2026-11-17-local-video-upload.md)을 따른다.

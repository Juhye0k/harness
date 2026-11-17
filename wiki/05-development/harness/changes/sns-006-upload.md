# SNS-006 — 확인된 출력만 한 번 업로드하기

> 외부 전송은 중복 실행과 성공 여부 불확실성을 함께 다뤄야 합니다. 확인한 출력만 보내도록 만든 계약, 발견한 결함과 회귀 검사, 검증 당시의 제한을 기록합니다.

[위키 홈](../../../README.md) · [개선 기록 목차](README.md)


## 작업 범위와 기준

사용자 요청은 지정한 분리 작업 트리에 6단계 SNS 업로드를 구현하는 것이다. 시작 커밋은 `228282dde8d5fb07a6df01c6313939fbeb6de373`, 브랜치는 `feat/sns-upload`다. 이후 사용자의 워크트리 반영·정리 요청에 따라 로컬 커밋과 기존 통합 브랜치 반영을 진행한다. 원격 푸시·Wiki 게시는 별도 지시가 없다. 기존 개발 스택과 별도 프로젝트·이미지·볼륨으로 검증한다. 원본 작업 트리의 미커밋 전사 변경과 비밀값을 가져오지 않는다.

완료 기준은 [YouTube 실행 계약](../../youtube-upload.md)과 같다. GPT-6.1 Sol/high 요청을 받았으나 현재 세션의 모델·추론 강도를 확인하거나 변경하는 도구는 제공되지 않았다. 관측 가능한 도구는 파일 편집·PowerShell·uv·Docker·pytest·Playwright와 공식 문서 조회다. 모델 토큰 사용량·비용은 도구가 제공하지 않아 알 수 없음이다. 일반 검사는 외부 게시·유료 AI 호출을 하지 않는다. 이후 사용자가 실제 계정 연결과 특정 출력의 비공개 업로드를 승인한 검증은 별도 로컬 환경과 비공개 기록으로 분리했다.

## 요구사항과 실행 가능한 검사

| ID | 조건·영향 | 구현 | 회귀 검사 |
|---|---|---|---|
| SNS-006-R01 | OAuth state 재사용·다른 브라우저 연결 방지 | [SNS API](../../../../app/api/sns.py), [저장소](../../../../app/adapters/sns_repository.py) | `test_state_is_owner_bound_expiring_and_single_use`, `test_http_approval_duplicate_and_oauth_security` |
| SNS-006-R02 | 확인한 계정·출력·제목·공개 범위·아동용 여부 고정 | [서비스](../../../../app/services/sns.py) | `test_approval_is_bound_to_exact_fields`, `test_stale_approval_is_rejected`, `test_stale_or_unapproved_upload_never_calls_provider` |
| SNS-006-R03 | 비공개 기본값·토큰 유출 방지 | [YouTube HTTP](../../../../app/adapters/youtube_upload.py), [로그 필터](../../../../app/adapters/sns_logging.py) | `test_http_adapter_sets_private_and_never_redirects_or_retries`, `test_session_capability_cannot_redirect_credentials`, `test_oauth_and_capability_logs_are_redacted` |
| SNS-006-R04 | 중복 확인·메시지 재전달·발행 경쟁에서 한 번만 전송 | [저장소](../../../../app/adapters/sns_repository.py) | `test_concurrent_confirmation_reuses_one_upload`, `test_sns_claim_waits_for_confirmation_dispatch_commit`, `test_redelivery_does_not_publish_again` |
| SNS-006-R05 | 불명확한 실패를 재전송하지 않고 상태만 확인 | [서비스](../../../../app/services/sns.py) | `test_ambiguous_result_only_probes_existing_session`, `test_probe_dispatch_claim_is_single_use_and_cannot_resend`, `test_duplicate_new_title_is_not_a_new_upload_and_interruption_is_unknown` |
| SNS-006-R06 | 브라우저의 동의·중복 클릭·새로고침·조회 오류 | [화면](../../../../app/static/sns.js) | `test_browser_explicit_confirmation_reload_and_query_error` |

검사는 [기본 대역](../../../../tests/unit/test_sns.py), [실제 DB](../../../../tests/integration/test_sns_database.py), [실제 HTTP·워커·브라우저](../../../../tests/integration/test_sns_flow.py)에 둔다. 테스트 수는 실제 플랫폼 품질 점수가 아니다.

## 발견과 수정

- Windows 공용 pytest 임시 폴더의 접근 제한으로 테스트 준비가 실패했다. worktree 안에 임시 부모 폴더를 생성하고 `--basetemp`를 지정해 기본 SNS 검사 29개를 통과했다. 테스트 assertion은 유지했다.
- 격리 통합 환경은 SNS를 의도적으로 켜므로, 환경 변수를 그대로 읽은 기본 비활성화 검사가 실패했다. 해당 검사만 환경 변수를 제거한 상태에서 설정 기본값을 확인하도록 수정했다.
- 로컬 필수 검사에서는 FFmpeg·FFprobe가 준비되지 않아 기존 영상 검사들이 실패했다. 해당 검사를 제외하지 않고 FFmpeg가 포함된 격리 이미지에서 동일 검사 진입점을 실행한다.
- 첫 전체 통합 검사는 51개 통과·SNS 브라우저 1개 실패였다. 테스트 호스트에서 `crypto.randomUUID()`를 사용할 수 없어 미리보기 제출이 멈췄다. `crypto.getRandomValues()`로 UUID를 생성하고 실패 시 버튼을 복구하도록 수정했다. 이후 브라우저 검사는 CSP를 우회하려는 문자열 평가 대신 영상의 실제 메타데이터를 직접 검사한다. 제품의 CSP는 약화하지 않았다.
- 수정 이미지 재빌드 중 Docker의 BuildKit·containerd 저장소가 `input/output error`를 반환했고 Windows 검사에서도 `WinError 112`(디스크 공간 부족)가 발생했다. 전역 캐시 정리·Docker 재시작·기존 개발 스택 변경은 하지 않았다. 이 작업에서 생성한 임시 폴더·Python/Ruff 캐시 약 26MB만 정리했다.
- 기존 설치된 FFmpeg·FFprobe 실행 파일을 프로세스 PATH에서 읽기 전용으로 참조해 최종 기본 검사를 수행했다. 원본 코드·전사 변경·비밀값을 복사하거나 수정하지 않았다.
- 이후 사용자가 캐시 정리와 Docker 재시작·기존 개발 컨테이너 복구를 명시적으로 승인했다. 재생성 가능한 임시 자료·이전 런타임·브라우저·Gradle 캐시 약 2.63GB를 정리했다. Docker는 빌드 캐시 10.35GB 회수를 보고했으며 Windows 여유 공간과 구분한다. 원본 저장소·비밀 설정·로그인 정보·DB 볼륨은 보존했다. 기존 개발 API와 별도 실제 계정 테스트 API의 DB·Redis 준비 상태를 확인했다.
- 실제 Google 동의 후 채널 조회가 실패해도 일반 연결 안내가 오류를 덮어쓰는 문제를 발견했다. 허용된 실패 코드만 기록하고 `CHANNEL_UNAVAILABLE`에는 고정된 안내를 전달한다. 브라우저는 계정 조회 후 오류 안내를 유지하며 성공한 연결도 표시한다. Windows 기본 파이프 인코딩으로 한글 치환이 누락된 실패를 브라우저 회귀 검사가 발견해 UTF-8로 다시 적용했다.

## 검증 결과와 남은 제한

- `uv sync --locked` 통과. `cryptography` 외 기존 의존성 버전 변경 없음.
- 최종 `uv run python scripts/verify.py`: Ruff·서식·기본 검사 **151개**·Alembic SQL 생성 통과. 통합 54개 제외. 캐시 생성을 끄고 worktree 전용 pytest 임시 경로를 지정했다. 이전 네트워크 차단·읽기 전용 격리 실행도 당시 기본 147개를 통과했다.
- SNS 기본 검사 **33개** 통과. Docker 복구 후 현재 소스·테스트를 읽기 전용으로 연결한 기존 이미지에서 전체 통합 검사 **54개**를 통과했다. PostgreSQL 경쟁·요청 번호 재사용, Redis·Celery, 실제 HTTP·Chromium과 OAuth 오류 안내 회귀 검사를 포함한다. 일반 검사는 가짜 AI·YouTube 제공자만 사용했다.
- 수정 후 브라우저 회귀 함수 `test_browser_explicit_confirmation_reload_and_query_error`를 별도 로컬 API와 설치된 Chrome에서 통과했다. 실제 SNS API·화면·합성 MP4·출력 고정 서비스에 메모리 저장소와 가짜 제공자를 주입했다. 미리보기·동의 전 전송 금지·중복 클릭·새로고침·조회 오류·390px 화면을 검사하고 데스크톱/모바일 이미지를 확인했다. 이 실행은 PostgreSQL·Redis·Celery 전체 재검증을 대신하지 않는다. 이미지·합성 영상·로컬 보조 실행 파일은 Git 제외 산출물이다.
- 최종 Ruff·서식·`git diff --check`와 변경 문서의 상대 링크를 확인한다. 기존 Starlette/httpx 사용 중단 예정 경고는 남아 있다.
- 격리 프로젝트는 `shortform-sns-84ae`, 전용 이미지는 `shortform-harness:sns-84ae-integration`이다. Docker 복구 후 추가 빌드 없이 현재 소스로 전체 통합 검사를 완료했다. 실제 계정 테스트는 별도 `shortform-sns-real-84ae` 프로젝트와 비공개 자격 증명을 사용하며 일반 통합 환경과 분리한다.

사용자 승인 후 실제 Google 동의·채널 연결과 합성 영상 1건의 비공개 업로드를 확인했다.

YouTube API에서 승인한 채널·제목·비공개·아동용 여부와 처리 완료를 확인했다.

원본 파일의 영상·음성·컨테이너는 각각 10.000초이며 YouTube 메타데이터는 11초로 반환됐다.

변환 차이 원인은 미확인이다.

처음 사용한 가로 영상은 Shorts 조건에 맞지 않아 사용자 지적 후 720×1280, 9:16, 음성 포함 10초의 별도 출력을 검증하고 새 승인 미리보기를 준비했다.

새 세로 출력은 별도 승인 후 1회 비공개 업로드했다.

YouTube API에서 720×1280·화면 비율 0.5625·비공개·아동용 아님·처리 완료를 확인했고, YouTube Studio의 Shorts 탭에서 새 영상 ID가 실제로 표시됨을 확인했다.

업로드 ID·영상 URL·자격 증명은 Git 제외된 로컬 기록에만 보관한다.

토큰 철회·플랫폼 업로드 제한·부하·운영 배포는 미검증이다.

자동 중단 감지·재시도·실패 작업의 재전송·다중 사용자 인증은 제공하지 않는다.

실제 업로드는 채널·출력 버전·제목·공개 범위에 대한 별도 명시적 승인 후에만 진행한다.

## 최종 통합과 정리 — 2026-11-17

- SNS 원본 커밋은 `a4e53b3c07ba2393ec39e39434dd1e2f8fb15ec3`이며 통합 시작 커밋은 `fb9b793d95ce21a819838e18971e3c525c5c43b2`다. SNS 기반이 이미 통합돼 있어 최종 OAuth 안내·회귀 검사·실제 검증 기록만 추가한다. 통합 브랜치의 워커 로그 보호, 초안 재작성과 SNS 저장소 경쟁 수정, 전사·자막 변경을 되돌리지 않는다.
- 기존 미커밋 변경은 Git 제외된 로컬 보존 기록과 대조한다. 실제 계정 설정·합성 영상·검증 기록은 공개 커밋에 넣지 않는다. 원격 푸시·Wiki 게시는 요청 범위에 없다.
- 정확한 커밋 후보는 기본 253개·실제 PostgreSQL·Redis·Celery·Chromium 통합 58개와 Ruff·서식·Alembic SQL 생성을 통과했다. 기존 전사·자막 미커밋 작업을 포함한 작업 폴더는 기본 284개를 통과했다. Windows 임시 경로 오류와 통합 전용 AI 환경변수 혼입은 별도 Linux 검사 환경 및 기본 환경 분리로 해결했다. 테스트 조건은 약화하지 않았다.
- 실계정 비공개 자료는 Git 제외 `.artifacts/sns-real-test-84ae`에 해시 검증해 보존했다. 실계정 테스트 컨테이너·네트워크만 제거하고 DB 볼륨과 게시된 영상은 보존한다. 별도 SNS 워크트리는 병합 이력 보존 후 제거한다.

<details>
<summary>작성 시점과 상태 이력</summary>

> 상태: 로컬 구현·기본/실제 인프라 통과·실제 비공개 Shorts 분류 확인 · 기준일: 2026-11-16 · 유지관리: 프로젝트 개발자

</details>

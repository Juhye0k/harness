# 추천 피드백과 반복 개선 — RECO-EVAL-001

같은 영상의 추천 후보를 사람이 평가하고, 수정 이유를 다음 실험과 회귀 검사에 반영한다. 먼저 수작업 평가를 진행한 뒤 반복 절차를 자동화하며, 후보 생성 성공과 추천 품질 향상을 구분한다.

> 상태: 로컬 도구 구현 / 실제 사람 평가·AI 작업자 연결 전

[위키 홈](../README.md) · [개발 목차](README.md)

## 먼저 수작업 1~3회

로컬 평가 UI는 `uv run python -m scripts.review_recommendations --directory <고정-평가-폴더> --source <로컬-원본> --port 8011`로 실행한다. 원본·전사 해시를 검사하고 localhost에만 바인딩한다. 웹에서 평가를 저장하면 별도 회차 폴더에 평가표·보고서·handoff.json을 보존하며, 평가 입력이 완료됐을 때 반복 루프 세션을 준비한다. 코딩 작업자 실행이나 외부 모델 호출을 자동 시작하지 않는다. 추천 후보가 없으면 원음·전사를 보며 기준 구간만 기록할 수 있고 품질 평가는 미완료로 남는다.

기존 추천 화면과 CLI로 `평가 → 문제 하나 수정 → 같은 입력으로 재검증`을 진행한다.
영상·전사·설정을 먼저 고정하고 선택한 후보, 사용 가능 여부, 수정할 구간, 이유를 기록한다.
미선택은 오답이 아니다. 선택 여부와 사용 가능 판정을 분리한다.
처음 결과와 마지막 결과, 관측된 사용량, 사람 개입, 실패 원인과 수정 내용을 비공개로 보관한다.
실제 영상·전사·평가 원문은 Git/Wiki에 게시하지 않는다.

```powershell
uv run python -m scripts.evaluate_recommendations capture <analysis-id> --source <local-original> --split development --output .artifacts/evaluations/round-01
uv run python -m scripts.evaluate_recommendations report .artifacts/evaluations/round-01
uv run python -m scripts.evaluate_recommendations compare .artifacts/evaluations/round-01/report.json .artifacts/evaluations/round-02/report.json --output .artifacts/evaluations/comparison-01.json
```

capture는 GET만 수행한다. source는 해당 분석의 원본임을 운영자가 확인한 로컬 파일이다.
현재 API는 서버 원본 해시를 반환하지 않으므로 서버 파일과의 동일성을 자동 인증하지 않는다.
도구는 로컬 원본 해시·영상 길이와 분석에 연결된 전사·장르·목적을 고정한다.
이후 비교는 이 입력과 평가 기준·development/holdout 구분이 일치해야 한다.
추천 모델·프롬프트 변경은 보고서의 configs에 남는다. 기존 해시 없는 평가 파일은 집계만 지원한다.

review.json에 reviewer와 각 후보의 usable, boundaries, independence를 입력한다.
selected는 선택 여부이며 null은 아직 선택 판단을 기록하지 않았다는 뜻이다.
uncertain=true는 판단 보류이며 usable은 null이어야 한다.
edited_range는 원본 기준 start_ms/end_ms다. 실제 후보·영상은 수정하지 않는다.
사용 불가 또는 구간 수정에는 reasons가 필요하다. 값은 preference, context, boundary,
transcription, duplicate, title, other이며 구체적 근거는 notes에 적는다.
snapshot_sha256은 그대로 유지한다. 다른 결과의 평가표를 재사용하지 않는다.
빈 후보·보류·미평가를 성공률 0이나 100%로 채우지 않는다. 비용 미제공은 null이다.
원인을 확정하지 못했다면 가설로 기록한다. 최종 확인용 결과로 반복 튜닝하지 않는다.

## 반복 실행 정책

평가 화면의 검토용 자막은 저장 전사의 원본 시각에 맞춰 표시된다. 단어별 시간이 없는 긴 구간은 원문 전체를 유지하므로 전체 문장 박스로 확인한다. 영상 위 표시를 끄거나 재생 위치를 탐색할 수 있으며, 이 미리보기는 영상 파일에 자막을 합성하거나 원본 전사를 편집하지 않는다.

정책 JSON은 사람이 검토한 명령 배열과 문제 목록이다. basic과 integration 검사는 필수다.
회귀 결함에는 그 결함을 재현하는 전용 check를 추가한다. 명령은 저장소 루트에서 실행한다.

```json
{
  "checks": {
    "basic": ["uv", "run", "python", "scripts/verify.py"],
    "integration": ["docker", "compose", "-f", "compose.integration.yaml", "run", "--rm", "runner"]
  },
  "issues": [{
    "id": "standalone-quality", "severity": "major", "verification": "human",
    "description": "원본을 몰라도 추천 내용을 이해할 수 있어야 한다",
    "evidence": "비공개 사람 평가 기록", "hypothesis": "", "proposed_fix": ""
  }],
  "worker": [],
  "command_timeout_seconds": 1800
}
```

```powershell
uv run python -m scripts.recommendation_loop init --policy .artifacts/evaluations/policy.json --output .artifacts/evaluations/loop-01
uv run python -m scripts.recommendation_loop record-evaluation .artifacts/evaluations/loop-01 --evaluation .artifacts/evaluations/round-01 --summary "기준 결과와 사람 피드백"
uv run python -m scripts.recommendation_loop check .artifacts/evaluations/loop-01 --seconds 3600
uv run python -m scripts.recommendation_loop status .artifacts/evaluations/loop-01
uv run python -m scripts.recommendation_loop confirm-human .artifacts/evaluations/loop-01 --issue standalone-quality --source-sha256 <status의-해시> --reviewer <사람> --evidence <확인-근거>
uv run python -m scripts.recommendation_loop run .artifacts/evaluations/loop-01 --seconds 7200
```

통합 환경은 검증 안내에 따라 미리 준비한다. 위 예시의 runner 명령은 이미지 빌드·인프라 준비를 대신하지 않는다.
check/run에는 회차 상한 대신 실행 시간 허용량이 필요하다. 한도 도달은 미완료다.
주요 문제의 연결 검사와 전체 검사가 같은 코드에서 연속 2회 통과하고, 사람 확인이 필요한
주요 항목이 현재 코드 해시에 대해 확인되어야 complete다. 코드 변경·실패·작업자 실행은 연속 통과를 초기화한다.
minor 항목은 목록에 남긴다. 문제의 중요도·검사 정책을 바꾸려면 사람이 새 세션을 준비한다.
등록한 정책의 완료이지 미등록 결함이 없다는 보장은 아니다. 사람 평가 기록의 진위는 도구가 인증하지 않는다.

## AI 작업자 연결과 제한

worker는 사용자가 별도로 준비한 로컬 코딩 작업자의 argv 배열이다. 내장 AI 클라이언트나 계정 연결은 없다.
작업자는 stdin으로 issues·last_check·change_approach·constraints JSON을 받고 코드를 수정한다.
종료 코드 0은 수정 작업 종료이며 품질 통과가 아니다. 하네스가 직접 모든 검사를 다시 실행한다.
두 번 이상 실패하면 change_approach=true로 다른 접근을 요청한다. 실패·시간 초과 시 실행은 미완료로 반환한다.
worker가 없으면 실패를 기록하고 수작업 수정을 기다린다. 횟수 3회 제한은 없다.

기존 테스트·검사 진입점·하네스·AGENTS.md는 세션 시작 시 해시를 고정한다.
작업자가 이를 수정하면 사람 검토가 필요하다. 새 회귀 테스트 추가는 허용한다.
append-only 이벤트에는 코드 해시·검사별 결과·사람 확인·평가·작업자 결과를 연결하며 기존 파일은 덮어쓰지 않는다.
동시 수정 실행은 execution.lock으로 거부한다. 강제 중단 후에는 실제 작업자 종료를 확인하고 잠금을 수동 해제한다.

명령 출력은 민감정보 유출을 피하려고 이벤트에 보관하지 않고 정제된 오류 코드만 기록한다.
argv의 실행 파일과 권한, 네트워크 차단은 실행 환경에서 관리한다. 이 도구는 샌드박스가 아니다.
기본 계약은 오프라인 수정이며 외부 AI·SNS·커밋·배포를 실행하지 않는다. 임의 작업자 명령의 외부 호출을
이 도구가 차단하거나 과금 한도를 강제하지는 않는다. 실제 외부 연동은 제공자·데이터·호출 한도 승인과
별도 강제 장치가 준비된 뒤 연결한다. 현재 구현을 유료 AI 자율 운영 완료로 설명하지 않는다.

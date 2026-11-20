# ADR-003 — Celery + Redis 채택과 Redis Streams 비교

> 작업 실행기를 직접 만드는 대신 Celery와 Redis로 영상 처리를 전달합니다. Redis Streams와의 차이, PostgreSQL에서 실행을 선점하는 이유, 자동 복구를 제공하지 않는 현재 한계를 설명합니다.


## 결정과 판단 기준

Python 영상 작업은 **Celery + Redis 브로커**로 전달한다. PostgreSQL에는 제품 상태를 저장하고 워커가 실행 직전에 조건부 선점을 요청한다. Redis Streams로 직접 작업 실행기를 만들지 않는다. 1인 개발에서는 메시지 처리기보다 영상 품질과 실패 검증에 개발 시간을 쓰는 것이 우선이다.

Celery는 작업 실행 프레임워크이고 Redis Streams는 로그 형태의 Redis 자료구조다. 비교 대상은 'Celery + Redis 전송 방식'과 'Streams + 직접 구현한 소비자/실행기'다. 현재 Celery Redis 전송은 Streams consumer group을 사용하지 않는다.

## 대안과 트레이드오프

| 항목 | Celery + Redis — 채택 | Streams + 직접 만든 워커 |
|---|---|---|
| 실행 관리 | 프로세스 풀·큐 라우팅·시간 제한·재시도 기능 제공 | 소비자 그룹 외 실행 풀·시간 제한·정책을 직접 연결 |
| 미확인 메시지 | ACK·visibility timeout 규칙 이해 필요 | PEL에서 추적하고 XACK·XAUTOCLAIM 등으로 관리 |
| 중복 안전성 | DB 조건부 선점 등 업무 검증 필요 | 재인수하더라도 업무 중복 안전성은 별도로 필요 |
| 보관·재생 | 업무 실행 대기열 중심 | 보관된 이벤트 재생·여러 소비자 그룹에 적합 |
| 확장 비용 | 큐별 워커 수 조절로 시작 | 세밀한 제어 대신 장애 처리·모니터링 개발 부담 |
| 이 프로젝트 | Python·FFmpeg 작업에 집중 가능 | 단순 작업 전달에 비해 직접 구현 범위가 큼 |

RabbitMQ + Celery도 적합하다. 라우팅·전달 정책 요구가 커지면 브로커 변경을 검토한다. Kafka는 여러 독립 소비자와 이벤트 재생이 제품 요구가 될 때 검토한다. 어느 선택도 인코딩 자체를 빠르게 하거나 DB·메시지·파일을 하나의 트랜잭션으로 만들지는 않는다.

## 왜 PostgreSQL에서 선점하는가

메시지를 워커에 배분하는 것은 Redis와 Celery다. PostgreSQL은 메시지를 가져오지 않는다. 워커는 받은 job_id에 대해 `queued → running` 변경에 성공한 경우에만 인코딩한다. 두 메시지가 같은 업무 ID를 가리키는 재발행·재전달 상황을 제품 상태와 함께 검증한다. 서로 다른 ID로 제출한 같은 URL은 차단하지 않는다.

워커 메모리는 다른 워커와 공유되지 않는다. Redis 락도 가능하지만 만료·프로세스 중단·DB 상태 반영을 함께 설계해야 한다. 이미 상태 기준인 PostgreSQL의 조건부 UPDATE를 사용해 관리 지점을 줄였다. 이는 전체 부작용의 exactly-once 보장이 아니다.

## 현재 정책과 한계

- 영상 큐 `video`, 진단 큐 `shortform`; 워커 concurrency 1, prefetch multiplier 1.
- 영상 태스크는 조기 ACK, 자동 재시도 없음, soft/hard 제한 660/720초. 진단은 240/300초 유지.
- Redis visibility timeout 900초. 강제 종료 감지나 자동 복구 타이머가 아니다.
- 일반 결과 backend 없음. PostgreSQL이 상태 기준이며 진단 테스트만 임시 Redis 결과 backend를 사용한다.
- 발행 전후 DB 갱신은 짧은 행 잠금으로 조정한다. 발행 동안 DB 연결을 점유하는 비용을 감수하며 인코딩 중에는 잠금을 잡지 않는다.
- API 종료 시 pending, 워커/DB 장애 시 running, 메시지 유실 시 queued가 남을 수 있다. outbox·주기 감시·자동 재실행은 없다.
- 발행 실패는 failed, 중단된 pending/running은 관리자가 실행 종료를 확인한 뒤 실패 처리한다. queued의 임의 실패 처리는 지원하지 않는다.

[상태 모델](../03-architecture/data-and-jobs.md)과 [관리자 절차](../05-development/async-video-jobs.md)를 함께 따른다.

## 확장과 재검토 조건

먼저 큐 대기 시간·인코딩 시간·CPU·메모리·실패율을 측정한다. 워커를 늘리기 전 자원 한도를 확인하고, 다중 호스트 전에는 객체 저장소를 도입한다. CPU 인코딩과 GPU 분석은 큐를 나눌 수 있다. 이용자 수 증가만으로 Streams로 교체하지 않는다.

발행 누락 복구가 필요하면 outbox, 실행 중단 복구가 필요하면 heartbeat/lease·시도 ID·오래된 실행 차단을 추가한다. 여러 서비스가 같은 이벤트 이력을 독립적으로 재생해야 한다면 Streams를 별도 ADR로 다시 평가한다.

## 공식 근거

2026-11-15 확인: [Celery Redis 전송·visibility timeout](https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/redis.html), [Redis Streams 소비자 그룹·확인·재인수](https://redis.io/docs/latest/develop/data-types/streams/). 기능 비교는 문서에 근거하며, 채택과 복구 범위는 이 프로젝트의 결정이다.

<details>
<summary>작성 시점과 상태 이력</summary>

> 상태: 채택 · VIDEO-002 로컬 구현 · 기준일: 2026-11-15 · 유지관리: 프로젝트 개발자

</details>

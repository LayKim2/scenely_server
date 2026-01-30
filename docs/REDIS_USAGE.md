# Redis 사용 내역

이 프로젝트에서 Redis는 **Celery 전용**으로만 사용됩니다. 애플리케이션 코드에서 직접 키/값을 넣거나 꺼내는 부분은 없습니다.

## Celery broker (메시지 큐)

- **역할**: Celery 태스크 큐. `process_job.delay(job_id)` 호출 시, “이 job_id로 process_job 실행해라” 메시지가 Redis 리스트에 들어갑니다.
- **저장 형태**: Celery가 정한 프로토콜(JSON 직렬화)로 태스크 이름, 인자, 옵션 등이 큐에 적재됩니다.
- **삭제 시점**: 워커가 해당 메시지를 소비해 태스크를 실행한 뒤 메시지는 제거됩니다.

## Celery result backend

- **역할**: 태스크 실행 결과/상태 저장. 태스크가 PENDING → STARTED → SUCCESS/FAILURE 로 바뀔 때마다 Redis에 상태가 기록됩니다.
- **저장 형태**: 태스크 ID를 키로, 상태/결과(또는 예외 정보)를 값으로 저장합니다. `process_job`은 반환값을 쓰지 않아도, Celery가 “완료됨/실패” 같은 메타데이터를 저장합니다.
- **삭제 시점**: Celery의 result_expires 설정에 따라 일정 시간 후 만료되거나, 수동으로 비우지 않는 한 유지됩니다.

## 정리

- **Redis에 들어가는 것**: Celery broker용 태스크 메시지 + Celery result backend용 태스크 상태/결과.
- **Redis에 들어가지 않는 것**: 유저 세션, 캐시, 애플리케이션 자체 키/값 데이터 등은 이 코드베이스에서 사용하지 않습니다.

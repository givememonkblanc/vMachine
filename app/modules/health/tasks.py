"""헬스 체크 관련 백그라운드 작업 정의"""

# TODO: Celery/Arq 태스크로 전환 시 아래 패턴 사용
#
# async def periodic_health_check(interval_seconds: int = 60) -> dict:
#     """주기적으로 전체 서비스 상태를 확인하고 결과를 저장합니다."""
#     ...

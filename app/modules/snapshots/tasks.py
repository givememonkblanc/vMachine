"""스냅샷 관련 백그라운드 작업 정의"""

# TODO: Celery/Arq 태스크로 전환 시 아래 패턴 사용
#
# async def create_scheduled_snapshot(server_id: str, retention: int = 7) -> str:
#     """스케줄된 VM 스냅샷을 생성하고 오래된 스냅샷을 정리합니다."""
#     ...

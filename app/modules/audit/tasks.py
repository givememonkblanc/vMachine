"""감사 로그 관련 백그라운드 작업 정의"""

# TODO: Celery/Arq 태스크로 전환 시 아래 패턴 사용
#
# async def cleanup_old_logs(retention_days: int = 90) -> int:
#     """일정 기간이 지난 감사 로그를 삭제합니다."""
#     ...

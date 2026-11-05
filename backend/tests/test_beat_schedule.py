from app.tasks.celery_app import BEAT_SCHEDULE


def test_backups_run_on_host_not_in_beat():
    tasks = {entry["task"] for entry in BEAT_SCHEDULE.values()}
    assert "tasks.backup.run_daily_backup" not in tasks
    assert "tasks.backup.run_redis_backup" not in tasks

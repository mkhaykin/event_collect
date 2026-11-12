# tests/collector/test_scheduler.py
from unittest.mock import patch

from apps.collector.scheduler import JobScheduler


def test_scheduler_register_and_due_jobs():
    """Проверка регистрации устройства и отбора готовых к запуску задач."""
    scheduler = JobScheduler()

    with patch("time.time", return_value=1000.0):
        # Регистрируем с немедленным запуском
        scheduler.register("dev-now", interval=300)
        # Регистрируем с отложенным запуском в будущем
        scheduler.register("dev-future", interval=300, next_run=1050.0)

        due = scheduler.get_due_jobs(current_time=1000.0)
        assert due == ["dev-now"]


def test_scheduler_running_lock_prevents_duplicate_runs():
    """Крайний случай: Пока задача помечена как running, она не должна попадать в get_due_jobs."""
    scheduler = JobScheduler()

    with patch("time.time", return_value=1000.0):
        scheduler.register("dev-1", interval=60)

        # Помечаем задачу запущенной
        scheduler.mark_started("dev-1")

        # Даже если время пошло вперед, пока задача не завершена, повторно её не отдаем
        assert scheduler.get_due_jobs(current_time=1010.0) == []
        # И при расчете времени сна running-задачи игнорируются
        assert scheduler.seconds_until_next() is None


def test_scheduler_mark_finished_success_and_retry():
    """Проверка пересчета расписания при успешном завершении и при сбое (ретрае)."""
    scheduler = JobScheduler()

    with patch("time.time", return_value=1000.0):
        scheduler.register("dev-1", interval=300)
        scheduler.mark_started("dev-1")

    # 1. Успешное завершение в момент 1005.0 -> следующий запуск через 300 сек (в 1305.0)
    with patch("time.time", return_value=1005.0):
        scheduler.mark_finished("dev-1", is_success=True, retry_delay_sec=60)
        assert scheduler._jobs["dev-1"].next_run == 1305.0
        assert "dev-1" not in scheduler._running

    # 2. Сбой выполнения в момент 1310.0 -> следующий запуск через retry_delay_sec (в 1370.0)
    scheduler.mark_started("dev-1")
    with patch("time.time", return_value=1310.0):
        scheduler.mark_finished("dev-1", is_success=False, retry_delay_sec=60)
        assert scheduler._jobs["dev-1"].next_run == 1370.0


def test_scheduler_ghost_device_protection():
    """Крайний случай: Если устройство удалили во время выполнения, mark_finished не воскресит его."""
    scheduler = JobScheduler()

    scheduler.register("ghost", interval=300)
    scheduler.mark_started("ghost")

    # Имитируем приход OFFLINE и удаление во время работы воркера
    scheduler.remove("ghost")

    # Воркер завершается
    scheduler.mark_finished("ghost", is_success=False, retry_delay_sec=60)

    assert "ghost" not in scheduler._jobs
    assert "ghost" not in scheduler._running


def test_scheduler_seconds_until_next():
    """Проверка точного расчета времени сна до ближайшей задачи."""
    scheduler = JobScheduler()

    # Пустое расписание возвращает None
    assert scheduler.seconds_until_next() is None

    scheduler.register("dev-later", interval=300, next_run=1100.0)
    scheduler.register("dev-sooner", interval=300, next_run=1025.0)

    with patch("time.time", return_value=1000.0):
        assert scheduler.seconds_until_next() == 25.0

    # Если время задачи уже прошло, сон должен быть строго 0.0 (без отрицательных значений)
    with patch("time.time", return_value=1030.0):
        assert scheduler.seconds_until_next() == 0.0

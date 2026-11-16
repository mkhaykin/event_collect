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


def test_scheduler_register_and_due_jobs():
    """Проверяет базовую регистрацию и правильность отбора готовых задач."""
    scheduler = JobScheduler()

    # Фиксируем время на отметке 1000.0
    with patch("time.time", return_value=1000.0):
        # dev-now должен запуститься прямо сейчас (next_run = 1000.0)
        scheduler.register("dev-now", interval=300)
        # dev-future планируется строго на 1050.0
        scheduler.register("dev-future", interval=300, next_run=1050.0)

        # Проверяем выборку при текущем времени 1000.0
        due = scheduler.get_due_jobs(current_time=1000.0)
        assert due == ["dev-now"]

        # Проверяем выборку позже, когда время подошло и для второго устройства
        due_later = scheduler.get_due_jobs(current_time=1060.0)
        assert sorted(due_later) == sorted(["dev-now", "dev-future"])


def test_scheduler_running_lock_execution():
    """Проверяет, что задачи со статусом 'running' исключаются изget_due_jobs и секунд сна."""
    scheduler = JobScheduler()

    with patch("time.time", return_value=1000.0):
        scheduler.register("dev-1", interval=60)

        # Переводим в статус выполнения
        scheduler.mark_started("dev-1")

        # Задача не должна быть доступна для повторного запуска, пока она выполняется
        assert scheduler.get_due_jobs(current_time=1010.0) == []
        # Расписание сна должно игнорировать выполняющуюся задачу
        assert scheduler.seconds_until_next() is None


def test_scheduler_seconds_until_next_calculation():
    """Проверяет, что seconds_until_next возвращает ЧИСТЫЕ СЕКУНДЫ сна (дельту), а не таймстамп."""
    scheduler = JobScheduler()

    # Если задач нет — возвращаем None (глубокий сон движка)
    assert scheduler.seconds_until_next() is None

    # Регистрируем две задачи на разное время в будущем
    scheduler.register("dev-soon", interval=300, next_run=1020.0)
    scheduler.register("dev-later", interval=300, next_run=1100.0)

    # При текущем времени 1000.0 до ближайшей задачи ровно 20.0 секунд
    with patch("time.time", return_value=1000.0):
        wait_time = scheduler.seconds_until_next()
        assert wait_time == 20.0  # Ожидаем чистую дельту, а не таймстамп 1020.0!

    # Если задача уже просрочена (например, время 1025.0), метод должен вернуть 0.0 (не спать)
    with patch("time.time", return_value=1025.0):
        wait_time = scheduler.seconds_until_next()
        assert wait_time == 0.0


def test_scheduler_mark_finished_intervals():
    """Проверяет расчет времени следующего запуска при успехе и ретрае."""
    scheduler = JobScheduler()

    # Старт системы в точке 1000.0
    with patch("time.time", return_value=1000.0):
        scheduler.register("dev-1", interval=300)  # Интервал 5 минут
        scheduler.mark_started("dev-1")

    # Сценарий 1: Успешное завершение опроса в точке 1005.0.
    # Задача должна переназначиться строго на 1005.0 + 300 = 1305.0
    with patch("time.time", return_value=1005.0):
        scheduler.mark_finished("dev-1", is_success=True, retry_delay_sec=60)
        assert scheduler._jobs["dev-1"].next_run == 1305.0
        assert "dev-1" not in scheduler._running

    # Сценарий 2: Провал опроса в точке 1310.0 (время подошло)
    scheduler.mark_started("dev-1")
    with patch("time.time", return_value=1310.0):
        scheduler.mark_finished("dev-1", is_success=False, retry_delay_sec=60)
        # Задача должна переназначиться по ретраю строго на 1310.0 + 60 = 1370.0
        assert scheduler._jobs["dev-1"].next_run == 1370.0


def test_scheduler_ghost_device_protection():
    """Крайний случай: Проверяет защиту от 'призраков', если устройство удалили во время опроса."""
    scheduler = JobScheduler()

    scheduler.register("ghost-device", interval=300)
    scheduler.mark_started("ghost-device")

    # Имитируем, что устройство удалили (пришел эвент OFFLINE), пока воркер собирал метрики
    scheduler.remove("ghost-device")

    # Воркер завершается (успешно или с ошибкой)
    scheduler.mark_finished("ghost-device", is_success=True)

    # Устройство НЕ должно воскреснуть в расписании
    assert "ghost-device" not in scheduler._jobs
    assert "ghost-device" not in scheduler._running

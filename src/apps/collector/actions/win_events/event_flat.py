# libs/collector/win_events/event_flat.py
import time
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class EventFlat:
    """Плоское представление системного события Windows для прямой записи в ClickHouse."""

    # Идентификация хоста
    system_computer: str
    system_channel: str

    # Блок System
    system_event_id: int
    system_event_record_id: int
    system_level: int
    system_version: int
    system_task: int
    system_opcode: int
    system_keywords: str

    # Блок Provider
    system_provider_name: str
    system_provider_guid: str
    system_provider_event_source_name: str
    system_provider_resource_file_name: str
    system_provider_message_file_name: str

    # Блок Event
    system_event_qualifiers: str

    # Блок Correlation
    system_correlation_activity_id: str
    system_correlation_related_activity_id: str

    # Блок Execution
    system_execution_process_id: int
    system_execution_thread_id: int

    # Блок Security
    system_security_user_id: str

    # Тяжелые текстовые поля
    message: str
    event_data: str
    user_data: str
    binary_data: str

    # Таймстампы
    system_time_created: str
    collected_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    # Метаданные сбора (наполняются на стороне коллектора)
    meta_collector_host: str = ""
    meta_script_version: str = ""

    def to_clickhouse_row(self) -> tuple:
        """Возвращает плоский кортеж данных, строго соответствующий порядку колонок в INSERT."""
        return (
            self.system_time_created,
            self.collected_at_ms,
            self.system_computer,
            self.system_channel,
            self.system_event_id,
            self.system_event_record_id,
            self.system_level,
            self.system_version,
            self.system_task,
            self.system_opcode,
            self.system_keywords,
            self.system_provider_name,
            self.system_provider_guid,
            self.system_provider_event_source_name,
            self.system_provider_resource_file_name,
            self.system_provider_message_file_name,
            self.system_event_qualifiers,
            self.system_correlation_activity_id,
            self.system_correlation_related_activity_id,
            self.system_execution_process_id,
            self.system_execution_thread_id,
            self.system_security_user_id,
            self.message,
            self.user_data,
            self.binary_data,
            self.event_data,
            self.meta_collector_host,
            self.meta_script_version,
        )

    @classmethod
    def get_column_names(cls) -> list[str]:
        """Возвращает имена колонок с точечной иерархией для передачи в клиент ClickHouse."""
        return [
            "system.time_created",
            "collected_at",
            "system.computer",
            "system.channel",
            "system.event_id",
            "system.event_record_id",
            "system.level",
            "system.version",
            "system.task",
            "system.opcode",
            "system.keywords",
            "system.provider.name",
            "system.provider.guid",
            "system.provider.event_source_name",
            "system.provider.resource_file_name",
            "system.provider.message_file_name",
            "system.event.qualifiers",
            "system.correlation.activity_id",
            "system.correlation.related_activity_id",
            "system.execution.process_id",
            "system.execution.thread_id",
            "system.security.user_id",
            "message",
            "user_data",
            "binary_data",
            "event_data",
            "meta.collector_host",
            "meta.script_version",
        ]

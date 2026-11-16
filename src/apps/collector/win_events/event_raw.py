# libs/collector/win_events/event_flat.py
from dataclasses import dataclass
from typing import Optional

from apps.collector.win_events.event_flat import EventFlat


@dataclass(frozen=True, slots=True)
class EventSystemProviderRaw:
    name: Optional[str]
    guid: Optional[str]
    event_source_name: Optional[str]
    resource_file_name: Optional[str] = None
    message_file_name: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "EventSystemProviderRaw":
        return cls(
            name=data.get("name"),
            guid=data.get("guid"),
            event_source_name=data.get("event_source_name"),
            resource_file_name=data.get("resource_file_name"),
            message_file_name=data.get("message_file_name"),
        )


@dataclass(frozen=True, slots=True)
class EventSystemEventRaw:
    qualifiers: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "EventSystemEventRaw":
        return cls(qualifiers=data.get("qualifiers"))


@dataclass(frozen=True, slots=True)
class EventSystemCorrelationRaw:
    activity_id: Optional[str]
    related_activity_id: Optional[str]

    @classmethod
    def from_dict(cls, data: dict) -> "EventSystemCorrelationRaw":
        return cls(
            activity_id=data.get("activity_id"),
            related_activity_id=data.get("related_activity_id"),
        )


@dataclass(frozen=True, slots=True)
class EventSystemExecutionRaw:
    process_id: Optional[str]
    thread_id: Optional[str]

    @classmethod
    def from_dict(cls, data: dict) -> "EventSystemExecutionRaw":
        return cls(
            process_id=data.get("process_id"),
            thread_id=data.get("thread_id"),
        )


@dataclass(frozen=True, slots=True)
class EventSystemSecurityRaw:
    user_id: Optional[str]

    @classmethod
    def from_dict(cls, data: dict) -> "EventSystemSecurityRaw":
        return cls(user_id=data.get("user_id"))


@dataclass(frozen=True, slots=True)
class EventSystemRaw:
    provider: EventSystemProviderRaw

    event_id: Optional[str]
    event_record_id: Optional[str]
    event: EventSystemEventRaw

    level: Optional[str]
    version: Optional[str]

    task: Optional[str]
    opcode: Optional[str]
    keywords: Optional[str]
    time_created: Optional[str]
    correlation: EventSystemCorrelationRaw
    execution: EventSystemExecutionRaw
    channel: Optional[str]
    computer: Optional[str]
    security: EventSystemSecurityRaw

    @classmethod
    def from_dict(cls, data: dict) -> "EventSystemRaw":
        return cls(
            provider=EventSystemProviderRaw.from_dict(data.get("provider", {})),
            event_id=data.get("event_id"),
            event_record_id=data.get("event_record_id"),
            event=EventSystemEventRaw.from_dict(data.get("event", {})),
            level=data.get("level"),
            version=data.get("version"),
            task=data.get("task"),
            opcode=data.get("opcode"),
            keywords=data.get("keywords"),
            time_created=data.get("time_created"),
            correlation=EventSystemCorrelationRaw.from_dict(data.get("correlation", {})),
            execution=EventSystemExecutionRaw.from_dict(data.get("execution", {})),
            channel=str(data.get("channel", "")),
            computer=str(data.get("computer", "")),
            security=EventSystemSecurityRaw.from_dict(data.get("security", {})),
        )


@dataclass(frozen=True, slots=True)
class EventRaw:
    system: EventSystemRaw
    event_data: Optional[str] = None
    binary_data: Optional[str] = None
    user_data: Optional[str] = None

    message: str = ""

    @classmethod
    def from_json(cls, json_data: dict) -> "EventRaw":
        return cls(
            system=EventSystemRaw.from_dict(json_data.get("system", {})),
            event_data=json_data.get("event_data"),
            user_data=json_data.get("user_data"),
            binary_data=json_data.get("binary_data"),
            message=json_data.get("message", ""),
        )

    # Кусок, который добавляется внутрь твоего базового датакласса EventRaw

    def to_flat(self, collector_host: str = "", script_version: str = "") -> EventFlat:
        """Преобразует иерархический EventRaw в плоский EventFlat для ClickHouse."""
        sys_raw = self.system
        prov = sys_raw.provider
        evt = sys_raw.event
        corr = sys_raw.correlation
        exec_raw = sys_raw.execution
        sec = sys_raw.security

        return EventFlat(
            system_time_created=sys_raw.time_created or "",
            system_computer=sys_raw.computer or "UNKNOWN",
            system_channel=sys_raw.channel or "UNKNOWN",
            # Конвертируем строки в числа, страхуясь от None через ленивый int()
            system_event_id=int(sys_raw.event_id) if sys_raw.event_id else 0,
            system_event_record_id=int(sys_raw.event_record_id) if sys_raw.event_record_id else 0,
            system_level=int(sys_raw.level) if sys_raw.level else 0,
            system_version=int(sys_raw.version) if sys_raw.version else 0,
            system_task=int(sys_raw.task) if sys_raw.task else 0,
            system_opcode=int(sys_raw.opcode) if sys_raw.opcode else 0,
            system_keywords=sys_raw.keywords or "",
            # Блок Provider
            system_provider_name=prov.name or "",
            system_provider_guid=prov.guid or "",
            system_provider_event_source_name=prov.event_source_name or "",
            system_provider_resource_file_name=prov.resource_file_name or "",
            system_provider_message_file_name=prov.message_file_name or "",
            # Блок Event
            system_event_qualifiers=evt.qualifiers or "",
            # Блок Correlation
            system_correlation_activity_id=corr.activity_id or "",
            system_correlation_related_activity_id=corr.related_activity_id or "",
            # Блок Execution
            system_execution_process_id=int(exec_raw.process_id) if exec_raw.process_id else 0,
            system_execution_thread_id=int(exec_raw.thread_id) if exec_raw.thread_id else 0,
            # Блок Security
            system_security_user_id=sec.user_id or "",
            # Тексты
            message=self.message or "",
            event_data=self.event_data or "",
            user_data=self.user_data or "",
            binary_data=self.binary_data or "",
            # Карта параметров и метаданные
            meta_collector_host=collector_host,
            meta_script_version=script_version,
        )

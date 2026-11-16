CREATE TABLE IF NOT EXISTS device_events
(
    `system.time_created` DateTime64(6, 'UTC'),
    `collected_at` DateTime64(3, 'UTC'),
    `system.computer` LowCardinality(String),
    `system.channel` LowCardinality(String),
    `system.event_id` UInt32,
    `system.event_record_id` UInt64,
    `system.level` UInt8,
    `system.version` UInt8,
    `system.task` UInt32,
    `system.opcode` UInt8,
    `system.keywords` String,
    `system.provider.name` LowCardinality(String),
    `system.provider.guid` String,
    `system.provider.event_source_name` LowCardinality(String),
    `system.provider.resource_file_name` String,
    `system.provider.message_file_name` String,
    `system.event.qualifiers` String,
    `system.correlation.activity_id` String,
    `system.correlation.related_activity_id` String,
    `system.execution.process_id` UInt32,
    `system.execution.thread_id` UInt32,
    `system.security.user_id` String,
    `message` String,
    `event_data` String,
    `user_data` String,
    `binary_data` String,
    `meta.collector_host` LowCardinality(String),
    `meta.script_version` LowCardinality(String)
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(`system.time_created`)
ORDER BY (`system.computer`, `system.channel`, `system.time_created`);

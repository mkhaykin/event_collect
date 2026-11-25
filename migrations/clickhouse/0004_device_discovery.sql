-- Нахождение устройств
CREATE TABLE IF NOT EXISTS device_discovery
(
    device_uid String,
    timestamp DateTime64(3, 'UTC'),
    status Enum8('created' = 0, 'updated' = 1, 'deleted' = 2),
    description JSON
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp) -- Партиционируем по месяцам, так как изменений состояний обычно меньше, чем пингов
ORDER BY (device_uid, timestamp);

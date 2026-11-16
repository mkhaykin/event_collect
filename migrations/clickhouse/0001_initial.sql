-- Результаты сетевых опросов устройств
CREATE TABLE IF NOT EXISTS device_probes
(
    uid String,
    timestamp DateTime64(3, 'UTC') DEFAULT now64(3, 'UTC'),
    is_success UInt8,                -- 1 = Успех, 0 = Ошибка/Таймаут
    latency_ms Float32,              -- Сетевая задержка
    packet_loss Float32,             -- Процент потерь пакетов (0.0 - 100.0)
    probes_sent UInt8,               -- Количество отправленных проб
    error_message LowCardinality(String) -- Сообщение об ошибке (пустая строка, если ошибок нет)
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)     -- Секционирование по месяцам (более эффективно для TTL, чем по дням)
ORDER BY (uid, timestamp)            -- Индексация для быстрой выборки истории по конкретному устройству
TTL timestamp + INTERVAL 1 WEEK DELETE; -- Автоматическая очистка данных старше недели



-- Изменение состояний устройств (онлайн/оффлайн)
CREATE TABLE IF NOT EXISTS device_states
(
    device_uid String,
    timestamp DateTime64(3, 'UTC'),
    status Enum8('offline' = 0, 'online' = 1) -- Enum экономит место и защищает от некорректных значений
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp) -- Партиционируем по месяцам, так как изменений состояний обычно меньше, чем пингов
ORDER BY (device_uid, timestamp);


-- Логи запуска и остановки служб (сервисов)
CREATE TABLE IF NOT EXISTS service_lifecycle
(
    service_name LowCardinality(String), -- Оптимизирует хранение строк с высокой повторяемостью (имена служб)
    timestamp DateTime64(3, 'UTC'),
    event Enum8('stopped' = 0, 'started' = 1)
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (service_name, timestamp);

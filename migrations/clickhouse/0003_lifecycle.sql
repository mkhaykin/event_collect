-- добавляем новую колонку session_id с нативным типом UUID
-- дефолт для старых данных (на момент миграции)
ALTER TABLE service_lifecycle
ADD COLUMN IF NOT EXISTS session_id UUID DEFAULT '00000000-0000-0000-0000-000000000000';

-- очищаем дефолт после наката миграции
ALTER TABLE service_lifecycle
MODIFY COLUMN session_id UUID;

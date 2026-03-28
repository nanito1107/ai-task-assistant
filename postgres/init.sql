-- ============================================================
--  AI Task Assistant - Inicialización de la Base de Datos
-- ============================================================

-- Extensiones
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Tabla de tareas
CREATE TABLE IF NOT EXISTS tasks (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title       TEXT NOT NULL,
    description TEXT,
    status      VARCHAR(20) NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'in_progress', 'completed', 'cancelled')),
    priority    VARCHAR(10) NOT NULL DEFAULT 'medium'
                CHECK (priority IN ('low', 'medium', 'high', 'urgent')),
    source      VARCHAR(20) DEFAULT 'telegram'
                CHECK (source IN ('telegram', 'api', 'voice', 'web')),
    due_date    TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    notified_at TIMESTAMPTZ,
    telegram_message_id BIGINT
);

-- Tabla de transcripciones de audio
CREATE TABLE IF NOT EXISTS transcriptions (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id     UUID REFERENCES tasks(id) ON DELETE CASCADE,
    audio_file  TEXT,
    transcript  TEXT NOT NULL,
    language    VARCHAR(10) DEFAULT 'es',
    model_used  VARCHAR(50),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Tabla de notificaciones enviadas
CREATE TABLE IF NOT EXISTS notifications (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id     UUID REFERENCES tasks(id) ON DELETE CASCADE,
    type        VARCHAR(30) NOT NULL,
    message     TEXT NOT NULL,
    sent_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    success     BOOLEAN DEFAULT true
);

-- Tabla de logs de AI
CREATE TABLE IF NOT EXISTS ai_logs (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id     UUID REFERENCES tasks(id) ON DELETE SET NULL,
    input       TEXT,
    output      TEXT,
    model       VARCHAR(50),
    tokens_used INTEGER,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Índices para Grafana y queries frecuentes
CREATE INDEX IF NOT EXISTS idx_tasks_status     ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_priority   ON tasks(priority);
CREATE INDEX IF NOT EXISTS idx_tasks_created    ON tasks(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tasks_due        ON tasks(due_date);
CREATE INDEX IF NOT EXISTS idx_tasks_source     ON tasks(source);
CREATE INDEX IF NOT EXISTS idx_notif_task       ON notifications(task_id);

-- Función para actualizar updated_at automáticamente
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_tasks_updated_at
    BEFORE UPDATE ON tasks
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- Vista para el dashboard de Grafana
CREATE OR REPLACE VIEW v_tasks_summary AS
SELECT
    DATE_TRUNC('day', created_at) AS day,
    status,
    priority,
    source,
    COUNT(*) AS total
FROM tasks
GROUP BY 1, 2, 3, 4;

-- Vista de tareas pendientes con alerta de vencimiento
CREATE OR REPLACE VIEW v_pending_alerts AS
SELECT
    id,
    title,
    priority,
    due_date,
    created_at,
    EXTRACT(EPOCH FROM (due_date - NOW()))/3600 AS hours_remaining
FROM tasks
WHERE status IN ('pending', 'in_progress')
  AND due_date IS NOT NULL
  AND due_date > NOW()
ORDER BY due_date ASC;

COMMENT ON TABLE tasks IS 'Tabla principal de tareas del asistente AI';

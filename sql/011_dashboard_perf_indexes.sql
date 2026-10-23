-- PRODESP — índices para consultas do dashboard de gestão (período + substatus + agendados)
-- MySQL não suporta CREATE INDEX IF NOT EXISTS — script idempotente via information_schema.
-- Executar conectado em prodesp_db: USE prodesp_db;

-- Filtro DATE(a.data_atendimentos) BETWEEN ...
SET @idx_exists := (
  SELECT COUNT(*) FROM information_schema.statistics
  WHERE table_schema = DATABASE()
    AND table_name = 'atendimentos'
    AND index_name = 'idx_atendimentos_data'
);
SET @sql := IF(
  @idx_exists > 0,
  'SELECT ''idx_atendimentos_data já existe'' AS msg',
  'CREATE INDEX idx_atendimentos_data ON atendimentos (data_atendimentos)'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- JOIN atendimentos ↔ unidades e NOT EXISTS em somente_agendado
SET @idx_exists := (
  SELECT COUNT(*) FROM information_schema.statistics
  WHERE table_schema = DATABASE()
    AND table_name = 'atendimentos'
    AND index_name = 'idx_atendimentos_unidade_data'
);
SET @sql := IF(
  @idx_exists > 0,
  'SELECT ''idx_atendimentos_unidade_data já existe'' AS msg',
  'CREATE INDEX idx_atendimentos_unidade_data ON atendimentos (id_unidades_atendimentos, data_atendimentos)'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Subquery ultimo_substatus_log (MAX por atendimento + tipo)
SET @idx_exists := (
  SELECT COUNT(*) FROM information_schema.statistics
  WHERE table_schema = DATABASE()
    AND table_name = 'atendimentos_status_log'
    AND index_name = 'idx_status_log_atend_tipo_alterado'
);
SET @sql := IF(
  @idx_exists > 0,
  'SELECT ''idx_status_log_atend_tipo_alterado já existe'' AS msg',
  'CREATE INDEX idx_status_log_atend_tipo_alterado ON atendimentos_status_log (id_atendimentos_log, tipo_campo_log, alterado_em_log)'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Filtro unidades agendadas no período
SET @idx_exists := (
  SELECT COUNT(*) FROM information_schema.statistics
  WHERE table_schema = DATABASE()
    AND table_name = 'unidades'
    AND index_name = 'idx_unidades_data_agendamento'
);
SET @sql := IF(
  @idx_exists > 0,
  'SELECT ''idx_unidades_data_agendamento já existe'' AS msg',
  'CREATE INDEX idx_unidades_data_agendamento ON unidades (data_agendamento_unidades)'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

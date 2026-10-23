-- PRODESP — índices para api/atendimentos_list (JOIN ult_sub_log_agg + filtros)
-- Complementa 011_dashboard_perf_indexes.sql e 012_observacoes_historico_indexes.sql.
-- Executar em prodesp_db. Idempotente via information_schema.
--
-- Nota: valor_novo_log é VARCHAR(50) no PRODESP — prefixo (80) gera erro MySQL 1089.

-- Prefixo seguro para colunas texto (VARCHAR/TEXT) — nunca maior que CHARACTER_MAXIMUM_LENGTH
SET @valor_log_prefix := (
  SELECT CASE
    WHEN DATA_TYPE IN ('text', 'mediumtext', 'longtext', 'tinytext') THEN '(50)'
    WHEN CHARACTER_MAXIMUM_LENGTH IS NULL OR CHARACTER_MAXIMUM_LENGTH = 0 THEN ''
    WHEN CHARACTER_MAXIMUM_LENGTH <= 50 THEN ''
    ELSE CONCAT('(', LEAST(CHARACTER_MAXIMUM_LENGTH, 50), ')')
  END
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'atendimentos_status_log'
    AND COLUMN_NAME = 'valor_novo_log'
  LIMIT 1
);
SET @valor_log_prefix := IFNULL(@valor_log_prefix, '');

SET @valor_hist_prefix := (
  SELECT CASE
    WHEN DATA_TYPE IN ('text', 'mediumtext', 'longtext', 'tinytext') THEN '(50)'
    WHEN CHARACTER_MAXIMUM_LENGTH IS NULL OR CHARACTER_MAXIMUM_LENGTH = 0 THEN ''
    WHEN CHARACTER_MAXIMUM_LENGTH <= 50 THEN ''
    ELSE CONCAT('(', LEAST(CHARACTER_MAXIMUM_LENGTH, 50), ')')
  END
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'historico'
    AND COLUMN_NAME = 'valor_novo_historico'
  LIMIT 1
);
SET @valor_hist_prefix := IFNULL(@valor_hist_prefix, '(50)');

-- Lookup / agregação ult_sub_log_agg: atendimento + tipo + substatus + timestamp
SET @idx_exists := (
  SELECT COUNT(*) FROM information_schema.statistics
  WHERE table_schema = DATABASE()
    AND table_name = 'atendimentos_status_log'
    AND index_name = 'idx_status_log_atend_tipo_valor_ts'
);
SET @sql := IF(
  @idx_exists > 0,
  'SELECT ''idx_status_log_atend_tipo_valor_ts já existe'' AS msg',
  CONCAT(
    'CREATE INDEX idx_status_log_atend_tipo_valor_ts ON atendimentos_status_log ',
    '(id_atendimentos_log, tipo_campo_log, valor_novo_log', @valor_log_prefix, ', alterado_em_log)'
  )
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Fallback historico (substatus) na agregação ult_sub_log_agg
SET @idx_exists := (
  SELECT COUNT(*) FROM information_schema.statistics
  WHERE table_schema = DATABASE()
    AND table_name = 'historico'
    AND index_name = 'idx_historico_atend_substatus_valor_ts'
);
SET @sql := IF(
  @idx_exists > 0,
  'SELECT ''idx_historico_atend_substatus_valor_ts já existe'' AS msg',
  CONCAT(
    'CREATE INDEX idx_historico_atend_substatus_valor_ts ON historico ',
    '(tabela_afetada_historico, campo_alterado_historico, id_registro_afetado_historico, ',
    'valor_novo_historico', @valor_hist_prefix, ', data_alteracao_historico)'
  )
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

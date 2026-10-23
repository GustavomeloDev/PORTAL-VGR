-- PRODESP — índices para observações (relatório) e historico (agenda as-of)
-- Executar em prodesp_db. Idempotente via information_schema.

SET @idx_exists := (
  SELECT COUNT(*) FROM information_schema.statistics
  WHERE table_schema = DATABASE()
    AND table_name = 'observacoes'
    AND index_name = 'idx_observacoes_timestamp'
);
SET @sql := IF(
  @idx_exists > 0,
  'SELECT ''idx_observacoes_timestamp já existe'' AS msg',
  'CREATE INDEX idx_observacoes_timestamp ON observacoes (timestamp_observacoes)'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @idx_exists := (
  SELECT COUNT(*) FROM information_schema.statistics
  WHERE table_schema = DATABASE()
    AND table_name = 'observacoes'
    AND index_name = 'idx_observacoes_atendimento'
);
SET @sql := IF(
  @idx_exists > 0,
  'SELECT ''idx_observacoes_atendimento já existe'' AS msg',
  'CREATE INDEX idx_observacoes_atendimento ON observacoes (id_atendimentos_observacoes, timestamp_observacoes)'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @idx_exists := (
  SELECT COUNT(*) FROM information_schema.statistics
  WHERE table_schema = DATABASE()
    AND table_name = 'historico'
    AND index_name = 'idx_historico_registro_campo'
);
SET @sql := IF(
  @idx_exists > 0,
  'SELECT ''idx_historico_registro_campo já existe'' AS msg',
  'CREATE INDEX idx_historico_registro_campo ON historico (tabela_afetada_historico, campo_alterado_historico, id_registro_afetado_historico)'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

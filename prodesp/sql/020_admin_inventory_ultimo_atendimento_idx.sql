-- PRODESP — índice para último atendimento por unidade (admin inventário).
-- Usado por MAX(id_atendimentos) GROUP BY id_unidades_atendimentos (listagem client).
-- Idempotente via information_schema.

SET @idx_exists := (
  SELECT COUNT(*) FROM information_schema.statistics
  WHERE table_schema = DATABASE()
    AND table_name = 'atendimentos'
    AND index_name = 'idx_atendimentos_unidade_id'
);
SET @sql := IF(
  @idx_exists > 0,
  'SELECT ''idx_atendimentos_unidade_id já existe'' AS msg',
  'CREATE INDEX idx_atendimentos_unidade_id ON atendimentos (id_unidades_atendimentos, id_atendimentos)'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

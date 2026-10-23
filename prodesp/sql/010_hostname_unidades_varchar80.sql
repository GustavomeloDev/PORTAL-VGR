-- PRODESP — amplia hostname para nomes longos (ex.: DETRAN com ID VGR no hostname)
-- Alinhar com COLUMN_LIMITS em prodesp/prodesp/db_field_limits.py (80).

ALTER TABLE `unidades`
  MODIFY COLUMN `hostname_unidades` VARCHAR(80) NULL DEFAULT NULL
    COMMENT 'Hostname do equipamento na unidade (até 80 caracteres)';

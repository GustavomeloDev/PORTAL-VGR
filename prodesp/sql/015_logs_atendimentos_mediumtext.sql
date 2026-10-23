-- PRODESP — amplia logs de configuração (coleta FGT + logs manuais)
-- Alinhar com LOGS_ATENDIMENTOS_MAX em prodesp/prodesp/db_field_limits.py (16 777 215).

ALTER TABLE `atendimentos`
  MODIFY COLUMN `logs_atendimentos` MEDIUMTEXT NULL
    COMMENT 'Logs de configuração remota (manual + coleta FGT)';

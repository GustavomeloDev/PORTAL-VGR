-- PRODESP — corrige triggers de atendimentos_status_log
--
-- Problema 1: NOT EXISTS (… valor_novo_log = NEW …) omitia reentradas.
-- Problema 2: UNIQUE uniq_log (id, tipo, valor_novo) bloqueia reentrada e o backfill.
-- Problema 3: backfill sem JOIN em atendimentos → FK 1452 quando historico tem
--             id_registro_afetado_historico órfão (ex.: id_vgr ou atendimento excluído).
--
-- Executar conectado em prodesp_db: USE prodesp_db;

DROP TRIGGER IF EXISTS trg_atendimentos_status_after_insert;
DROP TRIGGER IF EXISTS trg_atendimentos_status_after_update;

-- Remove UNIQUE que bloqueia reentrada (idempotente)
SET @idx_exists := (
  SELECT COUNT(*) FROM information_schema.statistics
  WHERE table_schema = DATABASE()
    AND table_name = 'atendimentos_status_log'
    AND index_name = 'uniq_log'
);
SET @sql := IF(
  @idx_exists > 0,
  'ALTER TABLE atendimentos_status_log DROP INDEX uniq_log',
  'SELECT ''uniq_log já removido'' AS msg'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Índice para MAX(alterado_em) por atendimento + tipo (011 — idempotente)
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

-- Remove linhas órfãs (impedem diagnóstico e podem indicar historico inconsistente)
DELETE s
FROM atendimentos_status_log s
LEFT JOIN atendimentos a ON a.id_atendimentos = s.id_atendimentos_log
WHERE a.id_atendimentos IS NULL;

DELIMITER $$

CREATE TRIGGER trg_atendimentos_status_after_insert
AFTER INSERT ON atendimentos
FOR EACH ROW
BEGIN
  IF NEW.id_atendimentos IS NOT NULL AND NEW.id_atendimentos > 0 THEN
    IF NEW.status_atendimentos IS NOT NULL AND TRIM(NEW.status_atendimentos) <> '' THEN
      INSERT INTO atendimentos_status_log (
        id_atendimentos_log,
        tipo_campo_log,
        valor_anterior_log,
        valor_novo_log,
        alterado_em_log
      )
      VALUES (
        NEW.id_atendimentos,
        'status',
        NULL,
        NEW.status_atendimentos,
        NOW()
      );
    END IF;

    IF NEW.substatus_atendimentos IS NOT NULL AND TRIM(NEW.substatus_atendimentos) <> '' THEN
      INSERT INTO atendimentos_status_log (
        id_atendimentos_log,
        tipo_campo_log,
        valor_anterior_log,
        valor_novo_log,
        alterado_em_log
      )
      VALUES (
        NEW.id_atendimentos,
        'substatus',
        NULL,
        NEW.substatus_atendimentos,
        NOW()
      );
    END IF;
  END IF;
END$$

CREATE TRIGGER trg_atendimentos_status_after_update
AFTER UPDATE ON atendimentos
FOR EACH ROW
BEGIN
  IF NEW.id_atendimentos IS NOT NULL AND NEW.id_atendimentos > 0 THEN
    IF NOT (OLD.status_atendimentos <=> NEW.status_atendimentos)
       AND NEW.status_atendimentos IS NOT NULL
       AND TRIM(NEW.status_atendimentos) <> '' THEN
      INSERT INTO atendimentos_status_log (
        id_atendimentos_log,
        tipo_campo_log,
        valor_anterior_log,
        valor_novo_log,
        alterado_em_log
      )
      VALUES (
        NEW.id_atendimentos,
        'status',
        OLD.status_atendimentos,
        NEW.status_atendimentos,
        NOW()
      );
    END IF;

    IF NOT (OLD.substatus_atendimentos <=> NEW.substatus_atendimentos)
       AND NEW.substatus_atendimentos IS NOT NULL
       AND TRIM(NEW.substatus_atendimentos) <> '' THEN
      INSERT INTO atendimentos_status_log (
        id_atendimentos_log,
        tipo_campo_log,
        valor_anterior_log,
        valor_novo_log,
        alterado_em_log
      )
      VALUES (
        NEW.id_atendimentos,
        'substatus',
        OLD.substatus_atendimentos,
        NEW.substatus_atendimentos,
        NOW()
      );
    END IF;
  END IF;
END$$

DELIMITER ;

-- Backfill: só registros cujo atendimento ainda existe (evita FK 1452)
INSERT INTO atendimentos_status_log (
  id_atendimentos_log,
  tipo_campo_log,
  valor_anterior_log,
  valor_novo_log,
  alterado_em_log
)
SELECT
  h.id_registro_afetado_historico,
  CASE
    WHEN h.campo_alterado_historico = 'substatus_atendimentos' THEN 'substatus'
    WHEN h.campo_alterado_historico = 'status_atendimentos' THEN 'status'
  END,
  NULLIF(TRIM(h.valor_antigo_historico), ''),
  NULLIF(TRIM(h.valor_novo_historico), ''),
  h.data_alteracao_historico
FROM historico h
INNER JOIN atendimentos a ON a.id_atendimentos = h.id_registro_afetado_historico
WHERE h.tabela_afetada_historico = 'atendimentos'
  AND h.campo_alterado_historico IN ('substatus_atendimentos', 'status_atendimentos')
  AND h.operacao_historico = 'UPDATE'
  AND h.valor_novo_historico IS NOT NULL
  AND TRIM(h.valor_novo_historico) <> ''
  AND NOT EXISTS (
    SELECT 1
    FROM atendimentos_status_log s
    WHERE s.id_atendimentos_log = h.id_registro_afetado_historico
      AND s.tipo_campo_log = CASE
            WHEN h.campo_alterado_historico = 'substatus_atendimentos' THEN 'substatus'
            ELSE 'status'
          END
      AND TRIM(s.valor_novo_log) = TRIM(h.valor_novo_historico)
      AND s.alterado_em_log = h.data_alteracao_historico
  );

-- Diagnóstico opcional: historico de atendimentos sem linha correspondente
-- SELECT h.id_log_historico, h.id_registro_afetado_historico, h.campo_alterado_historico,
--        h.valor_novo_historico, h.data_alteracao_historico
-- FROM historico h
-- LEFT JOIN atendimentos a ON a.id_atendimentos = h.id_registro_afetado_historico
-- WHERE h.tabela_afetada_historico = 'atendimentos'
--   AND h.campo_alterado_historico IN ('substatus_atendimentos', 'status_atendimentos')
--   AND a.id_atendimentos IS NULL
-- ORDER BY h.data_alteracao_historico DESC
-- LIMIT 50;

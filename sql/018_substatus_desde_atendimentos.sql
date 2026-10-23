-- PRODESP — P0-01 / Sprint 4: materializa instante de entrada no substatus atual
--
-- Executar em homolog primeiro: USE prodesp_db;
-- Depois: PRODESP_SUBSTATUS_DESDE_WRITE=true → backfill → PRODESP_SUBSTATUS_DESDE_READ=true
--
-- Rollback leitura: READ=0 (app volta à CTE). Coluna pode permanecer.

SET @col_exists := (
  SELECT COUNT(*) FROM information_schema.columns
  WHERE table_schema = DATABASE()
    AND table_name = 'atendimentos'
    AND column_name = 'substatus_desde_atendimentos'
);

SET @sql := IF(
  @col_exists > 0,
  'SELECT ''substatus_desde_atendimentos já existe'' AS msg',
  'ALTER TABLE atendimentos ADD COLUMN substatus_desde_atendimentos DATETIME NULL COMMENT ''Instante da última entrada no substatus_atendimentos atual (cronômetro Tempo Etapa)'' AFTER substatus_atendimentos'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Backfill a partir da mesma lógica da CTE ult_sub_log_agg (status_log ∪ historico)
UPDATE atendimentos a
INNER JOIN (
  SELECT
    id_atendimentos AS id_atend,
    substatus_nome AS sub_nome,
    MAX(ts) AS ultimo_ts
  FROM (
    SELECT
      s.id_atendimentos_log AS id_atendimentos,
      TRIM(s.valor_novo_log) AS substatus_nome,
      s.alterado_em_log AS ts
    FROM atendimentos_status_log s
    WHERE s.tipo_campo_log = 'substatus'
    UNION ALL
    SELECT
      h.id_registro_afetado_historico,
      TRIM(h.valor_novo_historico),
      h.data_alteracao_historico
    FROM historico h
    WHERE h.tabela_afetada_historico = 'atendimentos'
      AND h.campo_alterado_historico = 'substatus_atendimentos'
  ) u
  GROUP BY id_atendimentos, substatus_nome
) x
  ON x.id_atend = a.id_atendimentos
 AND x.sub_nome = TRIM(a.substatus_atendimentos)
SET a.substatus_desde_atendimentos = x.ultimo_ts
WHERE a.substatus_desde_atendimentos IS NULL
  AND a.substatus_atendimentos IS NOT NULL
  AND TRIM(a.substatus_atendimentos) <> '';

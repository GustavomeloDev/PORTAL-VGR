-- VGR 002 — logs de configuração no atendimento (paridade PRODESP / P1)
-- Banco: multi_cliente_db
-- Se a coluna já existir, o ALTER falha de forma segura (ignorar erro 1060).

ALTER TABLE atendimentos
  ADD COLUMN logs_configuracao MEDIUMTEXT NULL
    COMMENT 'Append de logs FGT/config (P1; limite alto)'
  AFTER observacoes;

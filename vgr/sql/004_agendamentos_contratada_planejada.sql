-- =============================================================================
-- VGR — Contratada planejada no agendamento (CSV Agendamento)
-- Espelho de prodesp/sql/008_planejada_unidades.sql, mas no modelo VGR a agenda
-- vive em `agendamentos` (não em `unidades`).
--
-- Aplicar DEPOIS de 001/002/003, com:  USE multi_cliente_db;
-- Idempotência: rodar uma única vez (MySQL 8 não tem ADD COLUMN IF NOT EXISTS).
-- =============================================================================

ALTER TABLE agendamentos
  ADD COLUMN id_contratada_planejada INT UNSIGNED NULL DEFAULT NULL
    COMMENT 'Contratada planejada pelo time de agendamento (CSV/portal); não cria atendimento'
    AFTER analista_livre,
  ADD KEY idx_ag_contratada_planejada (id_contratada_planejada),
  ADD CONSTRAINT fk_ag_contratada_planejada
    FOREIGN KEY (id_contratada_planejada) REFERENCES contratadas (id_contratada)
    ON DELETE SET NULL ON UPDATE CASCADE;

-- Busca do CSV por (equipamentos.id_vgr, equipamentos.tipo_servico).
-- Se já existir índice em id_vgr com outro nome, este composto continua útil.
ALTER TABLE equipamentos
  ADD KEY idx_equipamentos_id_vgr_tipo (id_vgr, tipo_servico);

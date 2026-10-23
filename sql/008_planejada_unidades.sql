-- PRODESP — Dados Field planejados no agendamento (CSV)
-- Colunas opcionais em unidades; não criam atendimento.
-- Valores efetivos permanecem em atendimentos.*_atendimentos.

ALTER TABLE `unidades`
  ADD COLUMN `contratada_planejada_unidades` VARCHAR(50) NULL DEFAULT NULL
    COMMENT 'Contratada planejada pelo time de agendamento (CSV)',
  ADD COLUMN `field_planejada_unidades` VARCHAR(60) NULL DEFAULT NULL
    COMMENT 'Field planejado pelo time de agendamento (CSV)',
  ADD COLUMN `contato_field_planejada_unidades` VARCHAR(255) NULL DEFAULT NULL
    COMMENT 'Contato Field planejado pelo time de agendamento (CSV)';

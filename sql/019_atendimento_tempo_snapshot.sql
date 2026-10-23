-- PRODESP — P0-02 / Sprint 5: snapshot de tempos (substitui JOIN na view no hot path)
--
-- USE prodesp_db;
-- Ordem: criar tabela → backfill → PRODESP_TEMPO_SNAPSHOT_WRITE=true →
--         validar → PRODESP_TEMPO_SNAPSHOT_READ=true
-- Rollback leitura: READ=0

CREATE TABLE IF NOT EXISTS atendimento_tempo_snapshot (
  id_atendimentos INT NOT NULL,
  id_unidade INT NULL,
  tempo_total_geral TIME NULL,
  tempo_total_atendimento TIME NULL,
  tempo_aguardando_cliente TIME NULL,
  tempo_triagem TIME NULL,
  tempo_aguarda_gestao TIME NULL,
  tempo_com_suporte TIME NULL,
  tempo_aguardando_config_remota TIME NULL,
  tempo_config_remota TIME NULL,
  tempo_aguardando_mpls TIME NULL,
  tempo_config_mpls TIME NULL,
  tempo_aguardando_caderno TIME NULL,
  tempo_caderno_teste TIME NULL,
  analista_atuante_atendimentos VARCHAR(255) NULL,
  analista_configuracao_atendimentos VARCHAR(255) NULL,
  analista_mpls_atendimentos VARCHAR(255) NULL,
  analista_caderno_teste_atendimentos VARCHAR(255) NULL,
  refreshed_at DATETIME NOT NULL,
  PRIMARY KEY (id_atendimentos),
  KEY idx_tempo_snap_refreshed (refreshed_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='Snapshot denormalizado de vw_tempo_atendimento_detalhado (P0-02)';

-- Backfill completo (pode demorar — rodar em janela calma)
INSERT INTO atendimento_tempo_snapshot (
  id_atendimentos, id_unidade,
  tempo_total_geral, tempo_total_atendimento, tempo_aguardando_cliente,
  tempo_triagem, tempo_aguarda_gestao, tempo_com_suporte,
  tempo_aguardando_config_remota, tempo_config_remota,
  tempo_aguardando_mpls, tempo_config_mpls,
  tempo_aguardando_caderno, tempo_caderno_teste,
  analista_atuante_atendimentos, analista_configuracao_atendimentos,
  analista_mpls_atendimentos, analista_caderno_teste_atendimentos,
  refreshed_at
)
SELECT
  v.id_atendimentos,
  v.id_unidade,
  v.tempo_total_geral,
  v.tempo_total_atendimento,
  v.tempo_aguardando_cliente,
  v.tempo_triagem,
  v.tempo_aguarda_gestao,
  v.tempo_com_suporte,
  v.tempo_aguardando_config_remota,
  v.tempo_config_remota,
  v.tempo_aguardando_mpls,
  v.tempo_config_mpls,
  v.tempo_aguardando_caderno,
  v.tempo_caderno_teste,
  v.analista_atuante_atendimentos,
  v.analista_configuracao_atendimentos,
  v.analista_mpls_atendimentos,
  v.analista_caderno_teste_atendimentos,
  NOW()
FROM vw_tempo_atendimento_detalhado v
ON DUPLICATE KEY UPDATE
  id_unidade = VALUES(id_unidade),
  tempo_total_geral = VALUES(tempo_total_geral),
  tempo_total_atendimento = VALUES(tempo_total_atendimento),
  tempo_aguardando_cliente = VALUES(tempo_aguardando_cliente),
  tempo_triagem = VALUES(tempo_triagem),
  tempo_aguarda_gestao = VALUES(tempo_aguarda_gestao),
  tempo_com_suporte = VALUES(tempo_com_suporte),
  tempo_aguardando_config_remota = VALUES(tempo_aguardando_config_remota),
  tempo_config_remota = VALUES(tempo_config_remota),
  tempo_aguardando_mpls = VALUES(tempo_aguardando_mpls),
  tempo_config_mpls = VALUES(tempo_config_mpls),
  tempo_aguardando_caderno = VALUES(tempo_aguardando_caderno),
  tempo_caderno_teste = VALUES(tempo_caderno_teste),
  analista_atuante_atendimentos = VALUES(analista_atuante_atendimentos),
  analista_configuracao_atendimentos = VALUES(analista_configuracao_atendimentos),
  analista_mpls_atendimentos = VALUES(analista_mpls_atendimentos),
  analista_caderno_teste_atendimentos = VALUES(analista_caderno_teste_atendimentos),
  refreshed_at = VALUES(refreshed_at);

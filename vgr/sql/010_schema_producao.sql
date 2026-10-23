-- =============================================================================
-- multi_cliente_db — schema de producao (banco novo)
-- Consolida: 000 + 001 + 003 + DMA 009/011/012/015
--
-- Campos de legado OMITIDOS (canonicos nas tabelas novas):
--   unidades.id_vgr              -> equipamentos.id_vgr
--   equipamentos.licenca         -> tabela licencas
--   atendimentos.logs_configuracao -> tabela coletas_configuracao
--
-- NAO aplicar 002_atendimento_logs_config.sql neste banco.
-- NAO aplicar os ALTER de backfill do 011 (id_vgr/licenca legado).
--
-- O modulo DMA consulta equipamentos.id_vgr e a tabela licencas (nao unidades.id_vgr
-- nem equipamentos.licenca). Logs FGT ficam em coletas_configuracao.
-- =============================================================================

CREATE DATABASE IF NOT EXISTS multi_cliente_db
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE multi_cliente_db;

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- -----------------------------------------------------------------------------
-- 1. Inventario
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS clientes (
  id_cliente INT UNSIGNED NOT NULL AUTO_INCREMENT,
  razao_social VARCHAR(255) NOT NULL,
  cnpj_cliente VARCHAR(18) NULL,
  endereco_principal VARCHAR(500) NULL,
  cidade VARCHAR(100) NULL,
  uf CHAR(2) NULL,
  cep VARCHAR(10) NULL,
  lider_tecnico VARCHAR(128) NULL COMMENT 'LT do cliente/projeto',
  nome_gp_cs_clientes VARCHAR(255) NULL COMMENT 'GP/CS do cliente/projeto',
  ativo TINYINT(1) NOT NULL DEFAULT 1,
  criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  atualizado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id_cliente),
  KEY idx_clientes_cnpj (cnpj_cliente),
  KEY idx_clientes_razao (razao_social),
  KEY idx_clientes_ativo (ativo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS unidades (
  id_unidade INT UNSIGNED NOT NULL AUTO_INCREMENT,
  id_cliente INT UNSIGNED NOT NULL,
  nome_unidade VARCHAR(255) NOT NULL,
  cnpj_unidade VARCHAR(18) NULL,
  codigo_unidade VARCHAR(64) NULL,
  codigo_identificacao VARCHAR(64) NULL,
  tipo_unidade VARCHAR(32) NULL DEFAULT 'FILIAL'
    COMMENT 'MATRIZ|FILIAL|…',
  topologia_unidades ENUM('Hub','Spoke') NULL,
  contato_unidade VARCHAR(255) NULL,
  endereco VARCHAR(500) NULL,
  bairro VARCHAR(120) NULL,
  cidade VARCHAR(100) NULL,
  uf CHAR(2) NULL,
  cep VARCHAR(10) NULL,
  latitude DECIMAL(10,8) NULL,
  longitude DECIMAL(11,8) NULL,
  ha TINYINT(1) NOT NULL DEFAULT 0
    COMMENT 'P12: unidade HA; exige 2 eq SDWAN antes de Agendado',
  ativo TINYINT(1) NOT NULL DEFAULT 1,
  criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  atualizado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id_unidade),
  KEY idx_unidades_cliente (id_cliente),
  KEY idx_unidades_codigo (codigo_unidade),
  KEY idx_unidades_cnpj (cnpj_unidade),
  KEY idx_unidades_ha (ha),
  KEY idx_unidades_ativo (ativo),
  CONSTRAINT fk_unidades_cliente
    FOREIGN KEY (id_cliente) REFERENCES clientes (id_cliente)
    ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS equipamentos (
  id_equipamento INT UNSIGNED NOT NULL AUTO_INCREMENT,
  id_unidade INT UNSIGNED NOT NULL,
  vendor VARCHAR(50) NULL COMMENT 'Fortinet|FortiGate|Meraki|TP-Link|Omada|Viptela|…',
  modelo VARCHAR(80) NULL,
  serial VARCHAR(100) NULL,
  hostname VARCHAR(80) NULL,
  id_vgr VARCHAR(32) NULL COMMENT 'ID VGR do equipamento (canonico)',
  fortcloud_key VARCHAR(255) NULL COMMENT 'ciphertext se sensivel',
  tipo_servico ENUM('SDWAN','SDWIFI','SDLAN') NULL,
  tkt_sae VARCHAR(64) NULL,
  tkt_noc VARCHAR(64) NULL,
  ativo TINYINT(1) NOT NULL DEFAULT 1,
  criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  atualizado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id_equipamento),
  UNIQUE KEY uq_equipamentos_serial (serial),
  KEY idx_equipamentos_unidade (id_unidade),
  KEY idx_equipamentos_vendor (vendor),
  KEY idx_equipamentos_tipo_servico (tipo_servico),
  KEY idx_equipamentos_hostname (hostname),
  KEY idx_equipamentos_id_vgr (id_vgr),
  CONSTRAINT fk_equipamentos_unidade
    FOREIGN KEY (id_unidade) REFERENCES unidades (id_unidade)
    ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS links (
  id_link INT UNSIGNED NOT NULL AUTO_INCREMENT,
  id_unidade INT UNSIGNED NOT NULL,
  id_equipamento INT UNSIGNED NULL
    COMMENT 'NULL = conectividade da unidade (LAN/loopback/…); preenchido = WAN no equipamento',
  tipo_link ENUM(
    'WAN','LAN','LOOPBACK_VIVO','LOOPBACK_CLIENTE','LOOPBACK_ON_BGP',
    'TRANSITO','TUNNEL','DHCP_SERVER','EXCLUDED_RANGE','AP_RANGE','REDE_VLAN'
  ) NOT NULL,
  modo_conexao ENUM('STATIC','DHCP','PPPOE','MPLS') NULL,
  ordem INT NULL,
  id_vgr_link VARCHAR(64) NULL,
  identificador VARCHAR(50) NULL,
  designador VARCHAR(100) NULL,
  ip_address VARCHAR(50) NULL,
  mascara VARCHAR(50) NULL,
  gateway VARCHAR(50) NULL,
  subrede VARCHAR(50) NULL,
  vlan VARCHAR(50) NULL,
  velocidade VARCHAR(50) NULL,
  operadora VARCHAR(100) NULL,
  contato_operadora VARCHAR(255) NULL COMMENT 'ciphertext se sensivel',
  telefone_reparo VARCHAR(255) NULL COMMENT 'ciphertext se sensivel',
  pppoe_user VARCHAR(255) NULL COMMENT 'ciphertext',
  pppoe_pass VARCHAR(255) NULL COMMENT 'ciphertext',
  range_start VARCHAR(50) NULL,
  range_end VARCHAR(50) NULL,
  ativo TINYINT(1) NOT NULL DEFAULT 1,
  criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  atualizado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id_link),
  KEY idx_links_unidade (id_unidade),
  KEY idx_links_equipamento (id_equipamento),
  KEY idx_links_tipo_ordem (tipo_link, ordem),
  KEY idx_links_id_vgr (id_vgr_link),
  CONSTRAINT fk_links_unidade
    FOREIGN KEY (id_unidade) REFERENCES unidades (id_unidade)
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT fk_links_equipamento
    FOREIGN KEY (id_equipamento) REFERENCES equipamentos (id_equipamento)
    ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS licencas (
  id_licenca INT UNSIGNED NOT NULL AUTO_INCREMENT,
  id_cliente INT UNSIGNED NOT NULL,
  id_equipamento INT UNSIGNED NULL
    COMMENT 'NULL = so no cliente (desassociada do equipamento)',
  codigo VARCHAR(120) NOT NULL,
  ordem TINYINT UNSIGNED NOT NULL DEFAULT 1
    COMMENT '1=licenca_01, 2=licenca_02',
  vendor VARCHAR(50) NULL COMMENT 'Vendor da licenca (ex. FORTINET)',
  modelo VARCHAR(80) NULL COMMENT 'Modelo da licenca (ex. FortiGate 40F)',
  ativo TINYINT(1) NOT NULL DEFAULT 1,
  criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  atualizado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id_licenca),
  KEY idx_licencas_cliente (id_cliente),
  KEY idx_licencas_equipamento (id_equipamento),
  KEY idx_licencas_codigo (codigo),
  KEY idx_licencas_vendor_modelo (vendor, modelo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS coletas_configuracao (
  id_coleta INT UNSIGNED NOT NULL AUTO_INCREMENT,
  modulo VARCHAR(32) NOT NULL COMMENT 'DMA, VGR, …',
  id_cliente INT UNSIGNED NOT NULL,
  id_unidade INT UNSIGNED NOT NULL,
  id_equipamento INT UNSIGNED NULL,
  id_atendimento INT UNSIGNED NULL COMMENT 'NULL se a coleta for so da unidade (ex.: DMA blueprint)',
  loopback VARCHAR(50) NULL,
  carimbo_texto MEDIUMTEXT NULL,
  logs_texto LONGTEXT NULL,
  admin_resumo TEXT NULL COMMENT 'Resumo da limpeza admin da coleta',
  sucesso TINYINT(1) NOT NULL DEFAULT 0,
  mensagem VARCHAR(500) NULL,
  usuario_re VARCHAR(16) NULL,
  usuario_nome VARCHAR(120) NULL,
  criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id_coleta),
  KEY idx_coleta_unidade (id_unidade, criado_em),
  KEY idx_coleta_cliente (id_cliente, criado_em),
  KEY idx_coleta_atend (id_atendimento),
  KEY idx_coleta_modulo (modulo, criado_em)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------------------------------
-- 2. Field (P10) — PII criptografado na aplicacao
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS contratadas (
  id_contratada INT UNSIGNED NOT NULL AUTO_INCREMENT,
  nome_contratada VARCHAR(255) NOT NULL,
  cnpj VARCHAR(18) NULL,
  ativo TINYINT(1) NOT NULL DEFAULT 1,
  criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  atualizado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id_contratada),
  KEY idx_contratadas_nome (nome_contratada),
  KEY idx_contratadas_cnpj (cnpj)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS fields (
  id_field INT UNSIGNED NOT NULL AUTO_INCREMENT,
  nome VARCHAR(128) NOT NULL,
  telefone VARCHAR(64) NULL,
  rg_enc VARCHAR(255) NULL COMMENT 'PII Fernet',
  cpf_enc VARCHAR(255) NULL COMMENT 'PII Fernet',
  ativo TINYINT(1) NOT NULL DEFAULT 1,
  criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  atualizado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id_field),
  KEY idx_fields_nome (nome),
  KEY idx_fields_telefone (telefone),
  KEY idx_fields_ativo (ativo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS field_emails (
  id_field_email INT UNSIGNED NOT NULL AUTO_INCREMENT,
  id_field INT UNSIGNED NOT NULL,
  email VARCHAR(255) NOT NULL,
  ordem TINYINT UNSIGNED NOT NULL DEFAULT 1,
  PRIMARY KEY (id_field_email),
  KEY idx_field_emails_field (id_field),
  CONSTRAINT fk_field_emails_field
    FOREIGN KEY (id_field) REFERENCES fields (id_field)
    ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS field_contratadas (
  id_field_contratada INT UNSIGNED NOT NULL AUTO_INCREMENT,
  id_field INT UNSIGNED NOT NULL,
  id_contratada INT UNSIGNED NOT NULL,
  inicio DATE NULL,
  fim DATE NULL,
  ativo TINYINT(1) NOT NULL DEFAULT 1,
  PRIMARY KEY (id_field_contratada),
  KEY idx_fc_field (id_field),
  KEY idx_fc_contratada (id_contratada),
  UNIQUE KEY uq_field_contratada_vigencia (id_field, id_contratada, inicio),
  CONSTRAINT fk_fc_field
    FOREIGN KEY (id_field) REFERENCES fields (id_field)
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT fk_fc_contratada
    FOREIGN KEY (id_contratada) REFERENCES contratadas (id_contratada)
    ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS field_historico (
  id_field_historico INT UNSIGNED NOT NULL AUTO_INCREMENT,
  id_field INT UNSIGNED NOT NULL,
  campo VARCHAR(64) NOT NULL,
  valor_antigo TEXT NULL,
  valor_novo TEXT NULL,
  usuario_re VARCHAR(16) NULL,
  usuario_nome VARCHAR(120) NULL,
  quando TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id_field_historico),
  KEY idx_fh_field (id_field),
  KEY idx_fh_quando (quando),
  CONSTRAINT fk_fh_field
    FOREIGN KEY (id_field) REFERENCES fields (id_field)
    ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------------------------------
-- 3. Agendamento + Atendimento (sem logs_configuracao)
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS agendamentos (
  id_agendamento INT UNSIGNED NOT NULL AUTO_INCREMENT,
  id_unidade INT UNSIGNED NOT NULL,
  status_agendamento VARCHAR(64) NOT NULL DEFAULT 'Pendente envio a logística',
  substatus_agendamento VARCHAR(64) NULL,
  data_agendamento DATE NULL,
  hora_agendamento TIME NULL,
  hora_inicio TIME NULL,
  hora_fim TIME NULL,
  tipo ENUM('Prateleira','Projeto Especial') NULL,
  analista_destino VARCHAR(120) NULL COMMENT 'RE/nome; NULL se livre',
  analista_livre TINYINT(1) NOT NULL DEFAULT 0,
  observacoes TEXT NULL,
  q_compra_equip TINYINT(1) NOT NULL DEFAULT 0,
  q_equip_mam TINYINT(1) NOT NULL DEFAULT 0,
  q_email_agendamento TINYINT(1) NOT NULL DEFAULT 0,
  q_lote TINYINT(1) NOT NULL DEFAULT 0,
  q_ticket_aberto TINYINT(1) NOT NULL DEFAULT 0,
  q_confirma_csi_gp TINYINT(1) NOT NULL DEFAULT 0,
  q_tem_problema TINYINT(1) NOT NULL DEFAULT 0,
  ativo TINYINT(1) NOT NULL DEFAULT 1,
  criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  atualizado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  criado_por_re VARCHAR(16) NULL,
  atualizado_por_re VARCHAR(16) NULL,
  PRIMARY KEY (id_agendamento),
  KEY idx_ag_unidade (id_unidade),
  KEY idx_ag_status (status_agendamento),
  KEY idx_ag_data (data_agendamento),
  KEY idx_ag_analista (analista_destino),
  KEY idx_ag_ativo_status (ativo, status_agendamento),
  CONSTRAINT fk_ag_unidade
    FOREIGN KEY (id_unidade) REFERENCES unidades (id_unidade)
    ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS atendimentos (
  id_atendimento INT UNSIGNED NOT NULL AUTO_INCREMENT,
  id_unidade INT UNSIGNED NOT NULL,
  id_agendamento INT UNSIGNED NULL
    COMMENT 'P3 1→1; NULL = walk-in sem agenda (P6)',
  status_atendimento VARCHAR(64) NOT NULL DEFAULT 'Em Atendimento',
  substatus_atendimento VARCHAR(64) NULL DEFAULT 'Aguarda Gestão',
  analista_atuante VARCHAR(120) NULL,
  atendimento_iniciado TINYINT(1) NOT NULL DEFAULT 0,
  abertura DATETIME NULL,
  fechamento DATETIME NULL,
  observacoes TEXT NULL,
  ativo TINYINT(1) NOT NULL DEFAULT 1,
  criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  atualizado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  criado_por_re VARCHAR(16) NULL,
  atualizado_por_re VARCHAR(16) NULL,
  PRIMARY KEY (id_atendimento),
  UNIQUE KEY uq_atend_agendamento (id_agendamento),
  KEY idx_atend_unidade (id_unidade),
  KEY idx_atend_status (status_atendimento),
  KEY idx_atend_substatus (substatus_atendimento),
  KEY idx_atend_analista (analista_atuante),
  KEY idx_atend_ativo (ativo),
  CONSTRAINT fk_atend_unidade
    FOREIGN KEY (id_unidade) REFERENCES unidades (id_unidade)
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT fk_atend_agendamento
    FOREIGN KEY (id_agendamento) REFERENCES agendamentos (id_agendamento)
    ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS agendamento_fields (
  id_agendamento_field INT UNSIGNED NOT NULL AUTO_INCREMENT,
  id_agendamento INT UNSIGNED NOT NULL,
  id_field INT UNSIGNED NOT NULL,
  ordem TINYINT UNSIGNED NOT NULL DEFAULT 1,
  snap_nome VARCHAR(128) NULL,
  snap_telefone VARCHAR(64) NULL,
  snap_rg_enc VARCHAR(255) NULL,
  snap_cpf_enc VARCHAR(255) NULL,
  snap_emails VARCHAR(500) NULL,
  snap_contratada_nome VARCHAR(255) NULL,
  id_contratada INT UNSIGNED NULL,
  criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id_agendamento_field),
  UNIQUE KEY uq_ag_field (id_agendamento, id_field),
  KEY idx_af_field (id_field),
  CONSTRAINT fk_af_agendamento
    FOREIGN KEY (id_agendamento) REFERENCES agendamentos (id_agendamento)
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT fk_af_field
    FOREIGN KEY (id_field) REFERENCES fields (id_field)
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT fk_af_contratada
    FOREIGN KEY (id_contratada) REFERENCES contratadas (id_contratada)
    ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS atendimento_fields (
  id_atendimento_field INT UNSIGNED NOT NULL AUTO_INCREMENT,
  id_atendimento INT UNSIGNED NOT NULL,
  id_field INT UNSIGNED NOT NULL,
  ordem TINYINT UNSIGNED NOT NULL DEFAULT 1,
  snap_nome VARCHAR(128) NULL,
  snap_telefone VARCHAR(64) NULL,
  snap_rg_enc VARCHAR(255) NULL,
  snap_cpf_enc VARCHAR(255) NULL,
  snap_emails VARCHAR(500) NULL,
  snap_contratada_nome VARCHAR(255) NULL,
  id_contratada INT UNSIGNED NULL,
  criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id_atendimento_field),
  UNIQUE KEY uq_at_field (id_atendimento, id_field),
  KEY idx_atf_field (id_field),
  CONSTRAINT fk_atf_atendimento
    FOREIGN KEY (id_atendimento) REFERENCES atendimentos (id_atendimento)
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT fk_atf_field
    FOREIGN KEY (id_field) REFERENCES fields (id_field)
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT fk_atf_contratada
    FOREIGN KEY (id_contratada) REFERENCES contratadas (id_contratada)
    ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------------------------------
-- 4. Auditoria
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS historico (
  id_historico INT UNSIGNED NOT NULL AUTO_INCREMENT,
  usuario_re VARCHAR(16) NULL,
  usuario_nome VARCHAR(120) NULL,
  tabela_afetada VARCHAR(64) NOT NULL,
  id_registro INT UNSIGNED NOT NULL,
  id_cliente INT UNSIGNED NULL,
  id_unidade INT UNSIGNED NULL,
  campo_alterado VARCHAR(255) NULL,
  valor_antigo TEXT NULL,
  valor_novo TEXT NULL,
  operacao ENUM('INSERT','UPDATE','DELETE') NOT NULL,
  data_alteracao TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id_historico),
  KEY idx_hist_tabela_reg (tabela_afetada, id_registro),
  KEY idx_hist_cliente (id_cliente),
  KEY idx_hist_unidade (id_unidade),
  KEY idx_hist_data (data_alteracao),
  CONSTRAINT fk_hist_cliente
    FOREIGN KEY (id_cliente) REFERENCES clientes (id_cliente)
    ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT fk_hist_unidade
    FOREIGN KEY (id_unidade) REFERENCES unidades (id_unidade)
    ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS agendamento_status_log (
  id_log INT UNSIGNED NOT NULL AUTO_INCREMENT,
  id_agendamento INT UNSIGNED NOT NULL,
  status_anterior VARCHAR(64) NULL,
  status_novo VARCHAR(64) NOT NULL,
  substatus_anterior VARCHAR(64) NULL,
  substatus_novo VARCHAR(64) NULL,
  usuario_re VARCHAR(16) NULL,
  usuario_nome VARCHAR(120) NULL,
  observacao TEXT NULL,
  criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id_log),
  KEY idx_asl_ag (id_agendamento),
  KEY idx_asl_criado (criado_em),
  CONSTRAINT fk_asl_ag
    FOREIGN KEY (id_agendamento) REFERENCES agendamentos (id_agendamento)
    ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS atendimento_status_log (
  id_log INT UNSIGNED NOT NULL AUTO_INCREMENT,
  id_atendimento INT UNSIGNED NOT NULL,
  status_anterior VARCHAR(64) NULL,
  status_novo VARCHAR(64) NOT NULL,
  substatus_anterior VARCHAR(64) NULL,
  substatus_novo VARCHAR(64) NULL,
  usuario_re VARCHAR(16) NULL,
  usuario_nome VARCHAR(120) NULL,
  observacao TEXT NULL,
  criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id_log),
  KEY idx_tsl_at (id_atendimento),
  KEY idx_tsl_criado (criado_em),
  CONSTRAINT fk_tsl_at
    FOREIGN KEY (id_atendimento) REFERENCES atendimentos (id_atendimento)
    ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET FOREIGN_KEY_CHECKS = 1;

-- =============================================================================
-- VGR (opcional): o cadastro VGR ainda pode ler unidades.id_vgr / equipamentos.licenca
-- / atendimentos.logs_configuracao. O DMA nao usa. Nao popular se descomentar.
-- =============================================================================
-- ALTER TABLE unidades
--   ADD COLUMN id_vgr VARCHAR(32) NULL COMMENT 'LEGADO. Canonico = equipamentos.id_vgr';
-- ALTER TABLE unidades ADD KEY idx_unidades_id_vgr (id_vgr);
--
-- ALTER TABLE equipamentos
--   ADD COLUMN licenca VARCHAR(255) NULL COMMENT 'LEGADO. Canonico = tabela licencas';
--
-- ALTER TABLE atendimentos
--   ADD COLUMN logs_configuracao MEDIUMTEXT NULL COMMENT 'LEGADO. Canonico = coletas_configuracao';

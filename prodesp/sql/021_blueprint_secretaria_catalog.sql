-- Catálogo de secretarias / Device Blueprint PRODESP (fonte de verdade runtime).
-- Aplicar no schema do módulo PRODESP (mesmo DB das unidades).

CREATE TABLE IF NOT EXISTS prodesp_blueprint_secretaria (
  id INT UNSIGNED NOT NULL AUTO_INCREMENT,
  acronimo VARCHAR(40) NOT NULL,
  nome_exibicao VARCHAR(120) NULL,
  ativo TINYINT(1) NOT NULL DEFAULT 1,
  device_blueprint_template VARCHAR(255) NOT NULL,
  layout_csv ENUM('rede_lan', 'legado') NOT NULL DEFAULT 'rede_lan',
  rede_lan_regra ENUM('nova', 'antiga') NOT NULL DEFAULT 'nova',
  aplica_sufixo_lan_dinamico TINYINT(1) NOT NULL DEFAULT 1,
  dhcp_lan_start_octeto VARCHAR(3) NULL,
  dhcp_lan_end_octeto VARCHAR(3) NULL,
  emite_dhcp_server_1 TINYINT(1) NOT NULL DEFAULT 0,
  legado_omitir_dhcp_server TINYINT(1) NOT NULL DEFAULT 0,
  mostrar_em_hint_ui TINYINT(1) NOT NULL DEFAULT 1,
  observacao VARCHAR(500) NULL,
  updated_at DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  updated_by VARCHAR(120) NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_bp_sec_acronimo (acronimo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS prodesp_blueprint_secretaria_alias (
  alias VARCHAR(40) NOT NULL,
  secretaria_id INT UNSIGNED NOT NULL,
  PRIMARY KEY (alias),
  KEY idx_bp_sec_alias_sec (secretaria_id),
  CONSTRAINT fk_bp_sec_alias_sec
    FOREIGN KEY (secretaria_id) REFERENCES prodesp_blueprint_secretaria (id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Seed idempotente (re-executável): upsert por acronimo canônico.
INSERT INTO prodesp_blueprint_secretaria (
  acronimo, nome_exibicao, ativo, device_blueprint_template, layout_csv, rede_lan_regra,
  aplica_sufixo_lan_dinamico, dhcp_lan_start_octeto, dhcp_lan_end_octeto,
  emite_dhcp_server_1, legado_omitir_dhcp_server, mostrar_em_hint_ui, observacao
) VALUES
  ('DETRAN', 'DETRAN', 1, 'DETRAN_HUB-C3-C4_40F_REDE_LAN_1', 'rede_lan', 'nova', 1, NULL, NULL, 0, 0, 1, NULL),
  ('DPESP', 'DPESP', 1, 'DPESP_HUB-C3-C4_40F_REDE_LAN_1', 'rede_lan', 'nova', 1, NULL, NULL, 0, 0, 1, NULL),
  ('SELJ', 'SELJ', 1, 'SE_HUB-C3-C4_40F_REDE_LAN_1', 'rede_lan', 'nova', 1, NULL, NULL, 0, 0, 1, 'Template device SE_…'),
  ('SAP', 'SAP', 1, 'SAP_HUB-C3-C4_40F_REDE_LAN_1', 'rede_lan', 'nova', 1, NULL, NULL, 1, 0, 1, 'Emite MV_dhcp_server_1_*'),
  ('SAPTELE', 'SAPTELE', 1, 'SAP-TELE_HUB-C5-C6_40F_REDE_LAN_1', 'rede_lan', 'nova', 1, NULL, NULL, 1, 0, 1, 'Hub C5-C6; alias SAP-TELE; emite dhcp_server_1'),
  ('DER', 'DER', 1, 'DER_HUB-C3-C4_40F_REDE_LAN_1', 'rede_lan', 'nova', 1, NULL, NULL, 0, 0, 1, NULL),
  ('SDE', 'SDE', 1, 'SDE_HUB-C3-C4_40F_REDE_LAN_1', 'rede_lan', 'nova', 1, NULL, NULL, 0, 0, 1, NULL),
  ('SEDS', 'SEDS', 1, 'SEDS_HUB-C3-C4_40F_REDE_LAN_1', 'rede_lan', 'antiga', 1, '10', '60', 0, 0, 1, 'Rede .0 + DHCP LAN .10–.60'),
  ('PROCON', 'PROCON', 1, 'PROCOM_HUB-C3-C4_40F_REDE_LAN_1', 'rede_lan', 'nova', 1, NULL, NULL, 0, 0, 1, 'Template device PROCOM_…'),
  ('PRO-SANGUE', 'PRO-SANGUE', 1, 'PROSANGUE_HUB-C3-C4_40F_REDE_LAN_1', 'rede_lan', 'nova', 1, NULL, NULL, 0, 0, 1, 'Cadastro com hífen; template sem hífen'),
  ('SP-AGUAS', 'SP-AGUAS', 1, 'SPAGUAS_HUB-C3-C4_40F_REDE_LAN_1', 'rede_lan', 'nova', 1, NULL, NULL, 0, 0, 1, 'Cadastro com hífen; template sem hífen'),
  ('CEETEPS', 'CEETEPS', 1, 'BP_CEETEPS_HUB-C3-C4_40F_REDE_LAN_1_VLAN_VOZ', 'rede_lan', 'nova', 1, NULL, NULL, 0, 0, 1, NULL),
  ('POUPATEMPO', 'POUPATEMPO', 1, 'PPT_HUB-C3-C4_40F_REDE_LAN_VOZ', 'rede_lan', 'nova', 0, NULL, NULL, 0, 0, 1, 'Sem sufixo LAN dinâmico'),
  ('DIPOL', 'DIPOL', 1, 'PCSPO_HUB-C3-C4_40F_REDE_LAN_1', 'legado', 'nova', 1, NULL, NULL, 0, 1, 1, 'Builder legado MV_10_; omite dhcp_server'),
  ('PGE', 'PGE', 1, 'PGE_HUB-C3-C4_HSW_40F_REDE_LAN_1', 'rede_lan', 'nova', 1, NULL, NULL, 0, 0, 1, NULL),
  ('TJSP', 'TJSP', 1, 'TJ_HUB-C1-C2_60F_REDE_LAN_1_VOZ_WIFI', 'rede_lan', 'nova', 1, NULL, NULL, 0, 0, 1, 'Hub C1-C2 + VOZ_WIFI'),
  ('CDHU', 'CDHU', 1, 'CDHU_HUB-C3-C4_40F_REDE_LAN_1', 'rede_lan', 'nova', 1, NULL, NULL, 0, 0, 1, NULL),
  ('JUSTICA', 'JUSTIÇA', 1, 'SJC_HUB-C3-C4_40F_REDE_LAN_1_VLAN_VOZ_ASSOC', 'rede_lan', 'nova', 1, NULL, NULL, 0, 0, 1, 'Canônico ASCII; alias JUSTIÇA'),
  ('FLORESTAL', 'FLORESTAL', 1, 'FLORESTAL_HUB-C1-C2_40F_REDE_LAN_1', 'rede_lan', 'nova', 1, NULL, NULL, 0, 0, 1, 'Hub C1-C2')
ON DUPLICATE KEY UPDATE
  nome_exibicao = VALUES(nome_exibicao),
  ativo = VALUES(ativo),
  device_blueprint_template = VALUES(device_blueprint_template),
  layout_csv = VALUES(layout_csv),
  rede_lan_regra = VALUES(rede_lan_regra),
  aplica_sufixo_lan_dinamico = VALUES(aplica_sufixo_lan_dinamico),
  dhcp_lan_start_octeto = VALUES(dhcp_lan_start_octeto),
  dhcp_lan_end_octeto = VALUES(dhcp_lan_end_octeto),
  emite_dhcp_server_1 = VALUES(emite_dhcp_server_1),
  legado_omitir_dhcp_server = VALUES(legado_omitir_dhcp_server),
  mostrar_em_hint_ui = VALUES(mostrar_em_hint_ui),
  observacao = VALUES(observacao);

-- Aliases (lookup único)
INSERT INTO prodesp_blueprint_secretaria_alias (alias, secretaria_id)
SELECT 'PROSANGUE', s.id FROM prodesp_blueprint_secretaria s WHERE s.acronimo = 'PRO-SANGUE'
ON DUPLICATE KEY UPDATE secretaria_id = VALUES(secretaria_id);

INSERT INTO prodesp_blueprint_secretaria_alias (alias, secretaria_id)
SELECT 'SPAGUAS', s.id FROM prodesp_blueprint_secretaria s WHERE s.acronimo = 'SP-AGUAS'
ON DUPLICATE KEY UPDATE secretaria_id = VALUES(secretaria_id);

INSERT INTO prodesp_blueprint_secretaria_alias (alias, secretaria_id)
SELECT 'JUSTIÇA', s.id FROM prodesp_blueprint_secretaria s WHERE s.acronimo = 'JUSTICA'
ON DUPLICATE KEY UPDATE secretaria_id = VALUES(secretaria_id);

INSERT INTO prodesp_blueprint_secretaria_alias (alias, secretaria_id)
SELECT 'SAP-TELE', s.id FROM prodesp_blueprint_secretaria s WHERE s.acronimo = 'SAPTELE'
ON DUPLICATE KEY UPDATE secretaria_id = VALUES(secretaria_id);

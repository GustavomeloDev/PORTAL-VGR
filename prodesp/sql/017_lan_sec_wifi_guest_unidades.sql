-- LAN SEC/TER/QUA + WiFi Guest (Blueprint).
-- Renomeia ip_lan_02_unidades → mv_ip_lan_sec_unidades e adiciona colunas opcionais.
-- Alinhado a prodesp/prodesp/db_field_limits.py (UNIDADES_LAN_EXTRA_SPEC / UNIDADES_MV_OPCIONAIS_SPEC).

-- VARCHAR(255): preserva tamanho legado de ip_lan_02_unidades (dados antigos > 45).
ALTER TABLE unidades
  CHANGE COLUMN ip_lan_02_unidades mv_ip_lan_sec_unidades VARCHAR(255) NULL DEFAULT NULL
    COMMENT 'Blueprint CSV: MV_IP_LAN_SEC (CIDR; máscara derivada na geração)';

ALTER TABLE unidades
  ADD COLUMN mv_rede_lan_sec_unidades VARCHAR(45) NULL DEFAULT NULL
    COMMENT 'Blueprint CSV: MV_REDE_LAN_SEC (IP rede, sem máscara)',
  ADD COLUMN mv_ip_lan_ter_unidades VARCHAR(45) NULL DEFAULT NULL
    COMMENT 'Blueprint CSV: MV_IP_LAN_TER (CIDR)',
  ADD COLUMN mv_rede_lan_ter_unidades VARCHAR(45) NULL DEFAULT NULL
    COMMENT 'Blueprint CSV: MV_REDE_LAN_TER',
  ADD COLUMN mv_ip_lan_qua_unidades VARCHAR(45) NULL DEFAULT NULL
    COMMENT 'Blueprint CSV: MV_IP_LAN_QUA (CIDR)',
  ADD COLUMN mv_rede_lan_qua_unidades VARCHAR(45) NULL DEFAULT NULL
    COMMENT 'Blueprint CSV: MV_REDE_LAN_QUA',
  ADD COLUMN mv_rede_wifi_guest_unidades VARCHAR(45) NULL DEFAULT NULL
    COMMENT 'Blueprint CSV: MV_REDE_WIFI_GUEST',
  ADD COLUMN mv_ip_wifi_guest_unidades VARCHAR(45) NULL DEFAULT NULL
    COMMENT 'Blueprint CSV: MV_IP_WIFI_GUEST (CIDR; máscara derivada na geração)',
  ADD COLUMN mv_dhcp_start_wifi_guest_unidades VARCHAR(45) NULL DEFAULT NULL
    COMMENT 'Blueprint CSV: MV_DHCP_START_WIFI_GUEST',
  ADD COLUMN mv_dhcp_end_wifi_guest_unidades VARCHAR(45) NULL DEFAULT NULL
    COMMENT 'Blueprint CSV: MV_DHCP_END_WIFI_GUEST',
  ADD COLUMN mv_reserva_start_wifi_guest_unidades VARCHAR(45) NULL DEFAULT NULL
    COMMENT 'Blueprint CSV: MV_RESERVA_START_WIFI_GUEST',
  ADD COLUMN mv_reserva_end_wifi_guest_unidades VARCHAR(45) NULL DEFAULT NULL
    COMMENT 'Blueprint CSV: MV_RESERVA_END_WIFI_GUEST';

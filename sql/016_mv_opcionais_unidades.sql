-- Campos opcionais MV_* do CSV de Blueprint (prefixo mv_ evita confusão com ip_lan_transito_unidades).
-- Alinhado a prodesp/prodesp/db_field_limits.py (UNIDADES_MV_OPCIONAIS_SPEC, 5º elemento = max_chars).

ALTER TABLE unidades
  ADD COLUMN mv_ip_transito_unidades VARCHAR(45) NULL DEFAULT NULL
    COMMENT 'Blueprint CSV: MV_IP_TRANSITO (Lan Trânsito opcional)',
  ADD COLUMN mv_mask_transito_unidades VARCHAR(45) NULL DEFAULT NULL
    COMMENT 'Blueprint CSV: MV_MASK_TRANSITO',
  ADD COLUMN mv_ip_swt_unidades VARCHAR(45) NULL DEFAULT NULL
    COMMENT 'Blueprint CSV: MV_IP_SWT (SWT)',
  ADD COLUMN mv_rede_voz_unidades VARCHAR(45) NULL DEFAULT NULL
    COMMENT 'Blueprint CSV: MV_REDE_VOZ',
  ADD COLUMN mv_mask_voz_unidades VARCHAR(45) NULL DEFAULT NULL
    COMMENT 'Blueprint CSV: MV_MASK_VOZ',
  ADD COLUMN mv_rede_lan_assoc_unidades VARCHAR(45) NULL DEFAULT NULL
    COMMENT 'Blueprint CSV: MV_REDE_LAN_ASSOC',
  ADD COLUMN mv_mask_lan_assoc_unidades VARCHAR(45) NULL DEFAULT NULL
    COMMENT 'Blueprint CSV: MV_MASK_LAN_ASSOC',
  ADD COLUMN mv_rede_totem_unidades VARCHAR(45) NULL DEFAULT NULL
    COMMENT 'Blueprint CSV: MV_REDE_TOTEM',
  ADD COLUMN mv_mask_totem_unidades VARCHAR(45) NULL DEFAULT NULL
    COMMENT 'Blueprint CSV: MV_MASK_TOTEM';

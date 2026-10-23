-- PRODESP — amplia colunas sensíveis para tokens Fernet (VARCHAR 255)
-- Executar ANTES do script migrate_encrypt_sensitive_fields.py

ALTER TABLE `atendimentos`
  MODIFY COLUMN `contato_field_atendimentos` VARCHAR(255) NULL DEFAULT NULL;

ALTER TABLE `unidades`
  MODIFY COLUMN `telefone_contato_unidades` VARCHAR(255) NULL DEFAULT NULL,
  MODIFY COLUMN `contato_field_planejada_unidades` VARCHAR(255) NULL DEFAULT NULL;

ALTER TABLE `links`
  MODIFY COLUMN `pppoe_user_links` VARCHAR(255) NULL DEFAULT NULL,
  MODIFY COLUMN `pppoe_pass_links` VARCHAR(255) NULL DEFAULT NULL;

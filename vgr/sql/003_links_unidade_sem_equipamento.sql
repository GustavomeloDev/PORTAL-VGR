-- VGR 003 — D3 revisado: conectividade de unidade (LAN+) sem equipamento;
-- WAN permanece com id_equipamento obrigatório (app).
-- Banco: multi_cliente_db

ALTER TABLE links
  MODIFY COLUMN id_equipamento INT UNSIGNED NULL
    COMMENT 'NULL = conectividade da unidade (LAN/loopback/…); NOT NULL = WAN no equipamento';

-- Desamarra inventário legado LAN+ do equipamento (compartilhado pela unidade).
UPDATE links
SET id_equipamento = NULL
WHERE tipo_link <> 'WAN'
  AND id_equipamento IS NOT NULL;

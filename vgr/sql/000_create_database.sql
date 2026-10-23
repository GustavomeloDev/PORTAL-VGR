-- =============================================================================
-- VGR / multi_cliente_db — criar database (aplicar como usuário com CREATE)
-- NÃO contém credenciais. Auth do Portal permanece em vgr_bd.
-- =============================================================================

CREATE DATABASE IF NOT EXISTS multi_cliente_db
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

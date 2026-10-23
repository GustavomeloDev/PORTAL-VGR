-- Redundante Crítico (MPLS + VIVO): flag 0/1 — IP efetivo permanece só em ip_wan_links.
-- Com flag=1 o WAN gravado já inclui +2; com flag=0 é o valor original da planilha.

ALTER TABLE links
  ADD COLUMN redundante_critico_links TINYINT(1) NOT NULL DEFAULT 0
    COMMENT '1 = Redundante Crítico (MPLS+VIVO): ip_wan_links gravado com +2'
    AFTER ip_wan_links;

# PORTAL-VGR
portal para suporte no atendimento em campo

## Módulos

| Pasta | Papel | Documentação |
|-------|-------|--------------|
| `core/` | Infraestrutura compartilhada (banco, logger, reports, utils, assets `/core/static`) | [`core/README.md`](core/README.md) |
| `prodesp/` | Portal PRODESP (Blueprint `prodesp_bp`, templates, static, SQL) e pacote de negócio `prodesp/prodesp/` | [`prodesp/docs/README.md`](prodesp/docs/README.md) |
| `vgr/` | Portal VGR (Blueprint `vgr_bp`) e pacote de negócio `vgr/vgr/` | [`vgr/vgr/README.md`](vgr/vgr/README.md) |

Os imports são absolutos a partir desta raiz (`from core...`, `from prodesp.prodesp...`),
portanto a raiz do repositório deve estar no `PYTHONPATH` / ser o diretório de execução do Flask.

-- vw_tempo_atendimento_detalhado (PRODESP)
--
-- View original + coluna tempo_aguardando_cliente (soma dos intervalos em base,
-- igual às demais colunas tempo_*).
--
-- data_fim: fim efetivo pelo log de status (Concluído tem prioridade sobre Quebra/Pendente
-- intermediários, ex. quebra revertida). Intervalos só são limitados a data_fim quando o
-- substatus começa antes desse instante.
--
-- Ajuste o nome do schema abaixo se não for prodesp_db.

create or replace
algorithm = UNDEFINED view `prodesp_db`.`vw_tempo_atendimento_detalhado` as
select
    `a`.`id_unidades_atendimentos` as `id_unidade`,
    `a`.`id_atendimentos` as `id_atendimentos`,
    date_format(`a`.`data_atendimentos`, '%d/%m/%Y') as `data_atendimentos`,
    `a`.`status_atendimentos` as `status_atendimentos`,
    `a`.`substatus_atendimentos` as `substatus_atendimentos`,
    `a`.`analista_atuante_atendimentos` as `analista_atuante_atendimentos`,
    `a`.`analista_configuracao_atendimentos` as `analista_configuracao_atendimentos`,
    `a`.`analista_mpls_atendimentos` as `analista_mpls_atendimentos`,
    `a`.`analista_caderno_teste_atendimentos` as `analista_caderno_teste_atendimentos`,
    `a`.`horario_inicio_atendimentos` as `horario_inicio_atendimentos`,
    cast(`f`.`data_fim` as time) as `horario_finalizacao_atendimentos`,
    sec_to_time(sum(`base`.`tempo_segundos`)) as `tempo_total_geral`,
    sec_to_time(sum((case when ((`base`.`substatus_atual` is not null) and (`base`.`substatus_atual` <> '') and (not((`base`.`substatus_atual` like '%Aguardando%')))) then `base`.`tempo_segundos` else 0 end))) as `tempo_total_atendimento`,
    sec_to_time(sum((case when (`base`.`substatus_atual` like '%Triagem%') then `base`.`tempo_segundos` else 0 end))) as `tempo_triagem`,
    sec_to_time(sum((case when (trim(`base`.`substatus_atual`) in ('Triagem', 'Aguarda Gestão')) then `base`.`tempo_segundos` else 0 end))) as `tempo_aguarda_gestao`,
    sec_to_time(sum((case when (trim(`base`.`substatus_atual`) = 'Com Suporte') then `base`.`tempo_segundos` else 0 end))) as `tempo_com_suporte`,
    sec_to_time(sum((case when (`base`.`substatus_atual` like '%Aguardando Config. Remota%') then `base`.`tempo_segundos` else 0 end))) as `tempo_aguardando_config_remota`,
    sec_to_time(sum((case when ((`base`.`substatus_atual` like '%Configuração Remota%') and (not((`base`.`substatus_atual` like '%Aguardando%')))) then `base`.`tempo_segundos` else 0 end))) as `tempo_config_remota`,
    sec_to_time(sum((case when (`base`.`substatus_atual` like '%Aguardando Config. MPLS%') then `base`.`tempo_segundos` else 0 end))) as `tempo_aguardando_mpls`,
    sec_to_time(sum((case when (`base`.`substatus_atual` like '%Configuração do MPLS%') then `base`.`tempo_segundos` else 0 end))) as `tempo_config_mpls`,
    sec_to_time(sum((case when (`base`.`substatus_atual` like '%Aguardando Caderno%') then `base`.`tempo_segundos` else 0 end))) as `tempo_aguardando_caderno`,
    sec_to_time(sum((case when (`base`.`substatus_atual` like '%Caderno de Teste%') then `base`.`tempo_segundos` else 0 end))) as `tempo_caderno_teste`,
    sec_to_time(sum((case when (trim(`base`.`substatus_atual`) = 'Aguardando Cliente') then `base`.`tempo_segundos` else 0 end))) as `tempo_aguardando_cliente`
from
    ((`prodesp_db`.`atendimentos` `a`
left join (
    select
        `s`.`id_atendimentos_log` as `id_atendimentos_log`,
        coalesce(
            max((case when ((`s`.`tipo_campo_log` = 'status') and (`s`.`valor_novo_log` = 'Concluído')) then `s`.`alterado_em_log` end)),
            max((case when ((`s`.`tipo_campo_log` = 'status') and regexp_like(`s`.`valor_novo_log`, 'Quebra|Pendente')) then `s`.`alterado_em_log` end))
        ) as `data_fim`
    from
        `prodesp_db`.`atendimentos_status_log` `s`
    group by
        `s`.`id_atendimentos_log`) `f` on
    ((`a`.`id_atendimentos` = `f`.`id_atendimentos_log`)))
left join (
    select
        `l`.`id_atendimentos_log` as `id_atendimentos_log`,
        `l`.`valor_novo_log` as `substatus_atual`,
        `l`.`alterado_em_log` as `alterado_em_log`,
        timestampdiff(second, `l`.`alterado_em_log`, coalesce(
            (case
                when (lead(`l`.`alterado_em_log`) over (partition by `l`.`id_atendimentos_log` order by `l`.`alterado_em_log`) is not null)
                    and (`f`.`data_fim` is not null)
                    and (`l`.`alterado_em_log` < `f`.`data_fim`)
                    and (lead(`l`.`alterado_em_log`) over (partition by `l`.`id_atendimentos_log` order by `l`.`alterado_em_log`) > `f`.`data_fim`)
                then `f`.`data_fim`
                else lead(`l`.`alterado_em_log`) over (partition by `l`.`id_atendimentos_log` order by `l`.`alterado_em_log`)
            end),
            (case
                when (`f`.`data_fim` is not null) and (`l`.`alterado_em_log` <= `f`.`data_fim`)
                then `f`.`data_fim`
            end)
        )) as `tempo_segundos`
    from
        ((
        select
            `x`.`id_log_atendimentos_status` as `id_log_atendimentos_status`,
            `x`.`id_atendimentos_log` as `id_atendimentos_log`,
            `x`.`tipo_campo_log` as `tipo_campo_log`,
            `x`.`valor_anterior_log` as `valor_anterior_log`,
            `x`.`valor_novo_log` as `valor_novo_log`,
            `x`.`alterado_em_log` as `alterado_em_log`,
            `x`.`prev_status` as `prev_status`
        from
            (
            select
                `l`.`id_log_atendimentos_status` as `id_log_atendimentos_status`,
                `l`.`id_atendimentos_log` as `id_atendimentos_log`,
                `l`.`tipo_campo_log` as `tipo_campo_log`,
                `l`.`valor_anterior_log` as `valor_anterior_log`,
                `l`.`valor_novo_log` as `valor_novo_log`,
                `l`.`alterado_em_log` as `alterado_em_log`,
                lag(`l`.`valor_novo_log`) over (partition by `l`.`id_atendimentos_log`
            order by
                `l`.`alterado_em_log` ) as `prev_status`
            from
                `prodesp_db`.`atendimentos_status_log` `l`
            where
                (`l`.`tipo_campo_log` = 'substatus')) `x`
        where
            (((`x`.`valor_novo_log` <> `x`.`prev_status`)
                or (`x`.`prev_status` is null))
                and (`x`.`valor_novo_log` is not null)
                    and (`x`.`valor_novo_log` <> ''))) `l`
    left join (
        select
            `s`.`id_atendimentos_log` as `id_atendimentos_log`,
            coalesce(
                max((case when ((`s`.`tipo_campo_log` = 'status') and (`s`.`valor_novo_log` = 'Concluído')) then `s`.`alterado_em_log` end)),
                max((case when ((`s`.`tipo_campo_log` = 'status') and regexp_like(`s`.`valor_novo_log`, 'Quebra|Pendente')) then `s`.`alterado_em_log` end))
            ) as `data_fim`
        from
            `prodesp_db`.`atendimentos_status_log` `s`
        group by
            `s`.`id_atendimentos_log`) `f` on
        ((`l`.`id_atendimentos_log` = `f`.`id_atendimentos_log`)))) `base` on
    ((`a`.`id_atendimentos` = `base`.`id_atendimentos_log`)))
group by
    `a`.`id_atendimentos`;

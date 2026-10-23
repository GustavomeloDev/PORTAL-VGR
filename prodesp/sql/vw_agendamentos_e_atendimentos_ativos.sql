-- =============================================================================

-- PRODESP — vw_agendamentos_e_atendimentos_ativos

-- =============================================================================

--

-- Ramo atendimentos:

--   1) As-of por atendimento: COALESCE(finalização, início) — não fim do dia civil.

--      Agenda no histórico só entra se data_alteracao_historico <= esse instante.

--      Dois atendimentos no mesmo dia não compartilham agenda cadastrada entre eles.

--   2) Calcula data/hora efetiva via histórico (valor_novo até as-of → valor_antigo do 1º log após
--      → INSERT tardio no mesmo dia quando não há visita posterior).
--      Não usa snapshot atual de unidades (evita “vazar” agenda futura para visitas anteriores).
--      Snapshot só se a unidade nunca teve log de agenda no histórico (legado).

--   3) Exibe agenda somente quando DATE(data_atendimentos) = DATE(agenda efetiva).

--

-- Ramo "Agendado" (sem id_atendimentos): mantém agenda atual da unidade (fila futura).

--

-- MySQL 8+. Ajuste o schema `prodesp_db` se necessário.

-- =============================================================================



CREATE OR REPLACE

ALGORITHM = UNDEFINED

SQL SECURITY INVOKER

VIEW `prodesp_db`.`vw_agendamentos_e_atendimentos_ativos` AS

WITH `atend_base` AS (

    SELECT

        `u`.`id_unidades` AS `id_unidades`,

        `a`.`id_atendimentos` AS `id_atendimentos`,

        `a`.`data_atendimentos` AS `data_atendimentos`,

        `a`.`status_atendimentos` AS `status_atendimentos`,

        `a`.`substatus_atendimentos` AS `substatus_atendimentos`,

        `a`.`analista_atuante_atendimentos` AS `analista_atuante_atendimentos`,

        `a`.`analista_configuracao_atendimentos` AS `analista_configuracao_atendimentos`,

        `a`.`analista_mpls_atendimentos` AS `analista_mpls_atendimentos`,

        `a`.`analista_caderno_teste_atendimentos` AS `analista_caderno_teste_atendimentos`,

        `a`.`horario_inicio_atendimentos` AS `horario_inicio_atendimentos`,

        `a`.`horario_finalizacao_atendimentos` AS `horario_finalizacao_atendimentos`,

        `u`.`nome_unidades` AS `nome_unidades`,

        `u`.`endereco_unidades` AS `endereco_unidades`,

        `u`.`id_vgr_unidades` AS `id_vgr_unidades`,

        `u`.`data_agendamento_unidades` AS `_u_data_agendamento`,

        `u`.`hora_agendamento_unidades` AS `_u_hora_agendamento`,

        COALESCE(

            TIMESTAMP(

                DATE(`a`.`data_atendimentos`),

                `a`.`horario_finalizacao_atendimentos`

            ),

            `a`.`data_atendimentos`

        ) AS `_as_of_ts`

    FROM

        `prodesp_db`.`atendimentos` `a`

        JOIN `prodesp_db`.`unidades` `u` ON `u`.`id_unidades` = `a`.`id_unidades_atendimentos`

),

`atend_com_agenda` AS (

    SELECT

        `b`.*,

        COALESCE(

            (

                SELECT STR_TO_DATE(TRIM(`h`.`valor_novo_historico`), '%Y-%m-%d')

                FROM `prodesp_db`.`historico` `h`

                WHERE `h`.`tabela_afetada_historico` = 'unidades'

                  AND `h`.`id_registro_afetado_historico` = `b`.`id_unidades`

                  AND `h`.`campo_alterado_historico` = 'data_agendamento_unidades'

                  AND TRIM(COALESCE(`h`.`valor_novo_historico`, '')) <> ''

                  AND `h`.`data_alteracao_historico` <= `b`.`_as_of_ts`

                ORDER BY `h`.`data_alteracao_historico` DESC, `h`.`id_log_historico` DESC

                LIMIT 1

            ),

            (

                SELECT STR_TO_DATE(LEFT(TRIM(`h`.`valor_antigo_historico`), 10), '%Y-%m-%d')

                FROM `prodesp_db`.`historico` `h`

                WHERE `h`.`tabela_afetada_historico` = 'unidades'

                  AND `h`.`id_registro_afetado_historico` = `b`.`id_unidades`

                  AND `h`.`campo_alterado_historico` = 'data_agendamento_unidades'

                  AND TRIM(COALESCE(`h`.`valor_antigo_historico`, '')) <> ''

                  AND `h`.`data_alteracao_historico` > `b`.`_as_of_ts`

                ORDER BY `h`.`data_alteracao_historico` ASC, `h`.`id_log_historico` ASC

                LIMIT 1

            ),

            (

                SELECT STR_TO_DATE(TRIM(`h`.`valor_novo_historico`), '%Y-%m-%d')

                FROM `prodesp_db`.`historico` `h`

                WHERE `h`.`tabela_afetada_historico` = 'unidades'

                  AND `h`.`id_registro_afetado_historico` = `b`.`id_unidades`

                  AND `h`.`campo_alterado_historico` = 'data_agendamento_unidades'

                  AND TRIM(COALESCE(`h`.`valor_novo_historico`, '')) <> ''

                  AND TRIM(COALESCE(`h`.`valor_antigo_historico`, '')) = ''

                  AND `h`.`data_alteracao_historico` > `b`.`_as_of_ts`

                  AND DATE(STR_TO_DATE(TRIM(`h`.`valor_novo_historico`), '%Y-%m-%d')) = DATE(`b`.`data_atendimentos`)

                  AND NOT EXISTS (

                      SELECT 1

                      FROM `prodesp_db`.`atendimentos` `a2`

                      WHERE `a2`.`id_unidades_atendimentos` = `b`.`id_unidades`

                        AND DATE(`a2`.`data_atendimentos`) = DATE(`b`.`data_atendimentos`)

                        AND `a2`.`data_atendimentos` > `b`.`_as_of_ts`

                        AND `a2`.`id_atendimentos` <> `b`.`id_atendimentos`

                  )

                ORDER BY `h`.`data_alteracao_historico` ASC, `h`.`id_log_historico` ASC

                LIMIT 1

            ),

            CASE

                WHEN NOT EXISTS (

                    SELECT 1

                    FROM `prodesp_db`.`historico` `hx`

                    WHERE `hx`.`tabela_afetada_historico` = 'unidades'

                      AND `hx`.`id_registro_afetado_historico` = `b`.`id_unidades`

                      AND `hx`.`campo_alterado_historico` IN (

                          'data_agendamento_unidades',

                          'hora_agendamento_unidades'

                      )

                )

                     AND `b`.`_u_data_agendamento` IS NOT NULL

                     AND DATE(`b`.`_u_data_agendamento`) <= DATE(`b`.`data_atendimentos`)

                    THEN `b`.`_u_data_agendamento`

            END

        ) AS `_agenda_data_efetiva`,

        COALESCE(

            (

                SELECT TRIM(`h`.`valor_novo_historico`)

                FROM `prodesp_db`.`historico` `h`

                WHERE `h`.`tabela_afetada_historico` = 'unidades'

                  AND `h`.`id_registro_afetado_historico` = `b`.`id_unidades`

                  AND `h`.`campo_alterado_historico` = 'hora_agendamento_unidades'

                  AND TRIM(COALESCE(`h`.`valor_novo_historico`, '')) <> ''

                  AND `h`.`data_alteracao_historico` <= `b`.`_as_of_ts`

                ORDER BY `h`.`data_alteracao_historico` DESC, `h`.`id_log_historico` DESC

                LIMIT 1

            ),

            (

                SELECT TRIM(`h`.`valor_antigo_historico`)

                FROM `prodesp_db`.`historico` `h`

                WHERE `h`.`tabela_afetada_historico` = 'unidades'

                  AND `h`.`id_registro_afetado_historico` = `b`.`id_unidades`

                  AND `h`.`campo_alterado_historico` = 'hora_agendamento_unidades'

                  AND TRIM(COALESCE(`h`.`valor_antigo_historico`, '')) <> ''

                  AND `h`.`data_alteracao_historico` > `b`.`_as_of_ts`

                ORDER BY `h`.`data_alteracao_historico` ASC, `h`.`id_log_historico` ASC

                LIMIT 1

            ),

            (

                SELECT TRIM(`h`.`valor_novo_historico`)

                FROM `prodesp_db`.`historico` `h`

                WHERE `h`.`tabela_afetada_historico` = 'unidades'

                  AND `h`.`id_registro_afetado_historico` = `b`.`id_unidades`

                  AND `h`.`campo_alterado_historico` = 'hora_agendamento_unidades'

                  AND TRIM(COALESCE(`h`.`valor_novo_historico`, '')) <> ''

                  AND TRIM(COALESCE(`h`.`valor_antigo_historico`, '')) = ''

                  AND `h`.`data_alteracao_historico` > `b`.`_as_of_ts`

                  AND EXISTS (

                      SELECT 1

                      FROM `prodesp_db`.`historico` `hd`

                      WHERE `hd`.`tabela_afetada_historico` = 'unidades'

                        AND `hd`.`id_registro_afetado_historico` = `b`.`id_unidades`

                        AND `hd`.`campo_alterado_historico` = 'data_agendamento_unidades'

                        AND TRIM(COALESCE(`hd`.`valor_novo_historico`, '')) <> ''

                        AND TRIM(COALESCE(`hd`.`valor_antigo_historico`, '')) = ''

                        AND `hd`.`data_alteracao_historico` > `b`.`_as_of_ts`

                        AND DATE(STR_TO_DATE(TRIM(`hd`.`valor_novo_historico`), '%Y-%m-%d')) = DATE(`b`.`data_atendimentos`)

                  )

                  AND NOT EXISTS (

                      SELECT 1

                      FROM `prodesp_db`.`atendimentos` `a2`

                      WHERE `a2`.`id_unidades_atendimentos` = `b`.`id_unidades`

                        AND DATE(`a2`.`data_atendimentos`) = DATE(`b`.`data_atendimentos`)

                        AND `a2`.`data_atendimentos` > `b`.`_as_of_ts`

                        AND `a2`.`id_atendimentos` <> `b`.`id_atendimentos`

                  )

                ORDER BY `h`.`data_alteracao_historico` ASC, `h`.`id_log_historico` ASC

                LIMIT 1

            ),

            CASE

                WHEN NOT EXISTS (

                    SELECT 1

                    FROM `prodesp_db`.`historico` `hx`

                    WHERE `hx`.`tabela_afetada_historico` = 'unidades'

                      AND `hx`.`id_registro_afetado_historico` = `b`.`id_unidades`

                      AND `hx`.`campo_alterado_historico` IN (

                          'data_agendamento_unidades',

                          'hora_agendamento_unidades'

                      )

                )

                     AND `b`.`_u_data_agendamento` IS NOT NULL

                     AND DATE(`b`.`_u_data_agendamento`) <= DATE(`b`.`data_atendimentos`)

                    THEN `b`.`_u_hora_agendamento`

            END

        ) AS `_agenda_hora_efetiva`

    FROM `atend_base` `b`

)

SELECT

    `id_unidades`,

    `id_atendimentos`,

    `data_atendimentos`,

    `status_atendimentos`,

    `substatus_atendimentos`,

    `analista_atuante_atendimentos`,

    `analista_configuracao_atendimentos`,

    `analista_mpls_atendimentos`,

    `analista_caderno_teste_atendimentos`,

    `horario_inicio_atendimentos`,

    `nome_unidades`,

    `endereco_unidades`,

    `id_vgr_unidades`,

    CASE

        WHEN `_agenda_data_efetiva` IS NOT NULL

             AND DATE(`data_atendimentos`) = DATE(`_agenda_data_efetiva`)

            THEN `_agenda_data_efetiva`

    END AS `data_agendamento_unidades`,

    CASE

        WHEN `_agenda_data_efetiva` IS NOT NULL

             AND DATE(`data_atendimentos`) = DATE(`_agenda_data_efetiva`)

            THEN `_agenda_hora_efetiva`

    END AS `hora_agendamento_unidades`

FROM `atend_com_agenda`

UNION ALL

SELECT

    `u`.`id_unidades` AS `id_unidades`,

    NULL AS `id_atendimentos`,

    NULL AS `data_atendimentos`,

    'Agendado' AS `status_atendimentos`,

    'Sem atendimento iniciado' AS `substatus_atendimentos`,

    NULL AS `analista_atuante_atendimentos`,

    NULL AS `analista_configuracao_atendimentos`,

    NULL AS `analista_mpls_atendimentos`,

    NULL AS `analista_caderno_teste_atendimentos`,

    NULL AS `horario_inicio_atendimentos`,

    `u`.`nome_unidades` AS `nome_unidades`,

    `u`.`endereco_unidades` AS `endereco_unidades`,

    `u`.`id_vgr_unidades` AS `id_vgr_unidades`,

    `u`.`data_agendamento_unidades` AS `data_agendamento_unidades`,

    `u`.`hora_agendamento_unidades` AS `hora_agendamento_unidades`

FROM

    `prodesp_db`.`unidades` `u`

WHERE

    `u`.`data_agendamento_unidades` IS NOT NULL

    AND NOT EXISTS (

        SELECT 1

        FROM `prodesp_db`.`atendimentos` `a2`

        WHERE `a2`.`id_unidades_atendimentos` = `u`.`id_unidades`

          AND CAST(`a2`.`data_atendimentos` AS DATE) >= `u`.`data_agendamento_unidades`

    );



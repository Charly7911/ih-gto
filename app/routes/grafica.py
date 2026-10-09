import MySQLdb
from flask import Blueprint, request, jsonify, render_template
from flask_login import login_required, current_user
from app import mysql
import calendar
from collections import defaultdict

grafica = Blueprint("grafica", __name__, url_prefix="/grafica")


@grafica.route("/")
@login_required
def grafica_home():
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    # 1. CONSULTA DE UNIDADES UNIFICADA
    # Usamos el catálogo como base para que el nombre sea el "oficial"
    # El INNER JOIN con la vista asegura que solo aparezcan unidades que tienen datos
    cur.execute("""
        SELECT DISTINCT 
            c.clues, 
            c.nombre_unidad 
        FROM catalogo_unidades c
        INNER JOIN vw_indicadores_unificados v ON c.clues = v.clues
        WHERE c.clues IS NOT NULL AND c.nombre_unidad IS NOT NULL
        ORDER BY c.nombre_unidad
    """)
    unidades_data = cur.fetchall()

    # 2. CONSULTA DE AÑOS REALES
    cur.execute("""
        SELECT DISTINCT anio 
        FROM vw_indicadores_unificados 
        WHERE anio IS NOT NULL 
        ORDER BY anio DESC
    """)
    anios_reales = [row["anio"] for row in cur.fetchall()]

    cur.close()

    # Fallback de años por seguridad
    if not anios_reales:
        anios_reales = [2023, 2024, 2025, 2026]

    return render_template(
        "grafica/grafica_by.html",
        show_grafica_menu=True,
        anios_disponibles=anios_reales,
        unidades=unidades_data,
    )


# ==========================================================
# FUNCIÓN TOTAL GENERAL (CON LOS 3 CASOS VALIDADOS)
# ==========================================================
def generar_total_general(
    data_acumulada,
    meses_validos,
    SUM_FIELDS,
    MAX_FIELDS,
    indicadores_max,
    calcular_kpis,
    es_descarga_masiva,
    indicadores_solicitados
):
    RECURSOS_FISICOS = [
        "camas_total", "quirofanos", "camas_med_int", "camas_cirugia",
        "camas_gineco", "camas_pediatria", "camas_otros", "hab_urgencias",
        "hab_observacion", "hab_quemados", "hab_lab_parto", "hab_recup_pp",
        "hab_cirug_amb", "hab_recup_pq", "hab_cuid_int", "hab_uci_adulto",
        "hab_uci_ped", "hab_otras_areas", "total_no_censables",
    ]

    if not data_acumulada:
        return []

    indicadores_solic_set = (
        {ind.lower() for ind in indicadores_solicitados}
        if isinstance(indicadores_solicitados, (list, set, tuple)) and indicadores_solicitados
        else set()
    )

    recursos_set = {r.lower() for r in RECURSOS_FISICOS}
    sum_fields_set = {s.lower() for s in SUM_FIELDS}

    # Unidades reales en data (excluyendo totales previos)
    unidades = {
        r.get("nombre_unidad")
        for r in data_acumulada
        if r.get("clues") != "TOTAL" and r.get("nombre_unidad") != "TOTAL GENERAL"
    }

    es_anual = any(r.get("mes") == 13 for r in data_acumulada)

    # Si solo hay 1 unidad y es vista anual, no genera fila extra
    if len(unidades) == 1 and es_anual:
        return []

    resultados = []

    # ==========================================
    # AUXILIAR: CONSTRUIR BASE (SUMA SOLO ABSOLUTOS)
    # ==========================================
    def construir_base(registros):
        base = {}

        # 1. Recursos Físicos
        recursos_map = defaultdict(lambda: defaultdict(float))
        for x in registros:
            indicador = x["indicador"].lower()
            unidad = x.get("nombre_unidad", "UNIDAD")
            if indicador in recursos_set:
                val = float(x.get("valor") or 0)
                if val > recursos_map[indicador][unidad]:
                    recursos_map[indicador][unidad] = val

        for campo in RECURSOS_FISICOS:
            base[campo] = sum(recursos_map[campo.lower()].values())

        # 2. Campos Sumables
        for campo in SUM_FIELDS:
            campo_lower = campo.lower()
            base[campo] = sum(
                float(x.get("valor") or 0)
                for x in registros
                if x["indicador"].lower() == campo_lower
            )

        # 3. Campos Máximos / Varios
        for campo in MAX_FIELDS:
            campo_lower = campo.lower()
            if campo_lower not in recursos_set and campo_lower not in sum_fields_set:
                base[campo] = sum(
                    float(x.get("valor") or 0)
                    for x in registros
                    if x["indicador"].lower() == campo_lower
                )

        return base

    # ==========================================
    # CASO 1: UNA SOLA UNIDAD - MENSUAL (CONSOLIDAR RANGO)
    # ==========================================
    if len(unidades) == 1 and not es_anual:
        anios_presentes = {r["anio"] for r in data_acumulada}

        for anio in anios_presentes:
            registros_anio = [
                r for r in data_acumulada
                if r["anio"] == anio and r.get("clues") != "TOTAL" and r.get("mes") != 13
            ]

            if not registros_anio:
                continue

            base = construir_base(registros_anio)
            meses_en_registro = {int(r["mes"]) for r in registros_anio}

            dias = sum(calendar.monthrange(anio, m)[1] for m in meses_en_registro)
            kpis = calcular_kpis(base, dias)
            dataset = {**base, **kpis}

            # Nota: Usamos el mes representativo (numérico) para no romper el ordenamiento de Chart.js
            mes_rep = max(meses_en_registro) if meses_en_registro else 12

            for indicador, valor in dataset.items():
                ind_lower = indicador.lower()
                if es_descarga_masiva or ind_lower in indicadores_solic_set:
                    resultados.append({
                        "anio": anio,
                        "mes": mes_rep,
                        "clues": "TOTAL",
                        "nombre_unidad": "TOTAL GENERAL",
                        "tipologia": "TODAS",
                        "indicador": ind_lower,
                        "valor": round(float(valor), 2)
                    })

        return resultados

    # ==========================================
    # CASO 2: VARIAS UNIDADES - ANUAL (MES 13)
    # ==========================================
    if len(unidades) > 1 and es_anual:
        anios_presentes = {r["anio"] for r in data_acumulada}

        for anio in anios_presentes:
            registros_anio = [
                r for r in data_acumulada
                if r["anio"] == anio and r.get("clues") != "TOTAL"
            ]

            if not registros_anio:
                registros_anio = [r for r in data_acumulada if r["anio"] == anio]

            base = construir_base(registros_anio)

            if meses_validos:
                dias = sum(calendar.monthrange(anio, m)[1] for m in meses_validos)
            else:
                dias = 365

            kpis = calcular_kpis(base, dias)
            dataset = {**base, **kpis}

            for indicador, valor in dataset.items():
                ind_lower = indicador.lower()
                if es_descarga_masiva or ind_lower in indicadores_solic_set:
                    resultados.append({
                        "anio": anio,
                        "mes": 13,
                        "clues": "TOTAL",
                        "nombre_unidad": "TOTAL GRUPO",
                        "tipologia": "TODAS",
                        "indicador": ind_lower,
                        "valor": round(float(valor), 2)
                    })

        return resultados

    # ==========================================
    # CASO 3: VARIAS UNIDADES - MENSUAL (DESGLOSE MES A MES)
    # ==========================================
    grupos = defaultdict(list)

    for r in data_acumulada:
        if r.get("clues") != "TOTAL":
            grupos[(r["anio"], int(r["mes"]))].append(r)

    # Fallback por si data_acumulada venía prefijada con TOTAL
    if not grupos:
        for r in data_acumulada:
            if r.get("mes") != 13:
                grupos[(r["anio"], int(r["mes"]))].append(r)

    for (anio, mes), registros in grupos.items():
        if mes == 13:
            continue

        base = construir_base(registros)
        dias = calendar.monthrange(anio, mes)[1]

        kpis = calcular_kpis(base, dias)
        dataset = {**base, **kpis}

        for indicador, valor in dataset.items():
            ind_lower = indicador.lower()
            if es_descarga_masiva or ind_lower in indicadores_solic_set:
                resultados.append({
                    "anio": anio,
                    "mes": mes,
                    "clues": "TOTAL",
                    "nombre_unidad": "TOTAL GRUPO",
                    "tipologia": "TODAS",
                    "indicador": ind_lower,
                    "valor": round(float(valor), 2)
                })

    return resultados




@grafica.route("/api/indicadores")
@login_required
def indicadores():

    cols_equipo_medico = []

    if not current_user.is_authenticated:
        return jsonify({
            "error": "sesion_expirada"
        }), 401


    kpis_calculados = [
        "especialidad",
        "especialidad_por_dia",
        "mental",
        "bucal",
        "consultas",
        "consultas_por_dia",
        "laboratorio",
        "rayosx",
        "ultrasonido",
        "electro",
        "encefa",
        "tac",
        "rnm",
        "anatomia",
        "calificada",
        "no_calificada",
        "porcentaje_calificada",
        "urgencias",
        "urgencias_por_dia",
        "medica",
        "accidentes",
        "pediatrica",
        "ginecobstetricia",
        "nac_eutocico",
        "nac_distocico",
        "nac_cesarea",
        "total_nacimientos",
        "nacimientos_por_dia",
        "porcentaje_cesareas",
        "abortos_lui",
        "abortos_ameu",
        "abortos_medicado",
        "abortos_no_especificado",
        "abortos_total",
        "eventos_obstetricos",
        "total_apeo",
        "porcentaje_apeo",
        "eventos_obstetricos_adolescentes",
        "adolescente_apeo",
        "porcentaje_adolescente_apeo",
        "egre_med_interna",
        "egre_cirugia",
        "egre_pediatria",
        "egre_gineco",
        "egre_otros",
        "total_egresos",
        "egre_med_int_48h",
        "egre_cirugia_48h",
        "egre_pediatria_48h",
        "egre_gineco_48h",
        "egre_otros_48h",
        "total_egresos_48h",
        "med_int_dentro",
        "cirugia_dentro",
        "gineco_dentro",
        "pediatria_dentro",
        "otros_dentro",
        "total_proced_dentro",
        "prom_inter_diarias_qx",
        "med_int_fuera",
        "cirugia_fuera",
        "gineco_fuera",
        "pediatria_fuera",
        "otros_fuera",
        "total_proced_fuera",
        "total_proced_med_int",
        "total_proced_cirugia",
        "total_proced_gineco",
        "total_proced_pediatria",
        "total_proced_otros",
        "total_proced",
        "egre_defunciones",
        "mortalidad_cruda",
        "egre_defunciones_48h",
        "mortalidad_ajustada",
        "dias_p_med_int",
        "dias_p_cirugia",
        "dias_p_gineco",
        "dias_p_pediatria",
        "dias_p_otros",
        "porcentaje_ocupacion",
        "porcentaje_ocupacion_med_interna",
        "porcentaje_ocupacion_cirugia",
        "porcentaje_ocupacion_pediatria",
        "porcentaje_ocupacion_gineco",
        "porcentaje_ocupacion_otros",
        "prom_dias_estancia",
        "indice_rotacion",
        "interv_sustitucion",
        "camas_total",
        "camas_med_int",
        "camas_cirugia",
        "camas_gineco",
        "camas_pediatria",
        "camas_otros",
        "quirofanos",
        "hab_urgencias",
        "hab_observacion",
        "hab_quemados",
        "hab_lab_parto",
        "hab_recup_pp",
        "hab_cirug_amb",
        "hab_recup_pq",
        "hab_cuid_int",
        "hab_uci_adulto",
        "hab_uci_ped",
        "hab_otras_areas",
        "total_no_censables",
    ]

    # ==========================================================
    # CAMPOS SUMABLES
    # ==========================================================
    SUM_FIELDS = [
        "total_egresos",
       "dias_est_med",
        "dias_est_cir",
        "dias_est_ped",
        "dias_est_gin",
        "dias_est_otros",
        "egre_med_interna",
        "egre_cirugia",
        "egre_pediatria",
        "egre_gineco",
        "egre_otros",
        "egre_defunciones",
        "egre_defunciones_48h",
        "dias_estancia",
        "dias_p",
        "apeo",
        "consultas",
        "especialidad",
        "mental",
        "bucal",
        "laboratorio",
        "rayosx",
        "anatomia",
        "electro",
        "encefa",
        "ultrasonido",
        "tac",
        "rnm",
        "dias_p_med_int",
        "dias_p_cirugia",
        "dias_p_gineco",
        "dias_p_pediatria",
        "dias_p_otros",
        "urgencias",
        "calificada",
        "no_calificada",
        "medica",
        "accidentes",
        "pediatrica",
        "ginecobstetricia",
        # 👇 ESTOS SON LOS IMPORTANTES
        "nac_cesarea",
        "total_nacimientos",
        "nac_eutocico",
        "nac_distocico",
        "abortos",
        "abortos_ameu",
        "abortos_lui",
        "abortos_medicado",
        "abortos_no_especificado",
        "abortos_total",
        "eventos_obstetricos",
        "total_apeo",
        "cirugias",
        "adolescente_apeo",
        "eventos_obstetricos_adolescentes",
        "egre_med_int_48h",
        "egre_cirugia_48h",
        "egre_pediatria_48h",
        "egre_gineco_48h",
        "egre_otros_48h",
        "total_egresos_48h",
        "med_int_dentro",
        "cirugia_dentro",
        "gineco_dentro",
        "pediatria_dentro",
        "otros_dentro",
        "total_proced_dentro",
        "med_int_fuera",
        "cirugia_fuera",
        "gineco_fuera",
        "pediatria_fuera",
        "otros_fuera",
        "total_proced_fuera",
        "total_proced_med_int",
        "total_proced_cirugia",
        "total_proced_gineco",
        "total_proced_pediatria",
        "total_proced_otros",
        "total_proced",
        "dias_cama_total",
        "dias_cama_med",
        "dias_cama_cir",
        "dias_cama_gin",
        "dias_cama_ped",
        "dias_cama_otros",
    ]


    #PARTE 2
    # ==========================================================
    # CAMPOS MAX
    # ==========================================================
    MAX_FIELDS = [
        "camas_total",
        "quirofanos",
        "camas_med_int",
        "camas_cirugia",
        "camas_gineco",
        "camas_pediatria",
        "camas_otros",
        "hab_urgencias",
        "hab_observacion",
        "hab_quemados",
        "hab_lab_parto",
        "hab_recup_pp",
        "hab_cirug_amb",
        "hab_recup_pq",
        "hab_cuid_int",
        "hab_uci_adulto",
        "hab_uci_ped",
        "hab_otras_areas",
        "total_no_censables",
    ]

    indicadores_equipo_medico = {
        "arco_c_analogo",
        "arco_c_digital",
        "bascula_estadimetro",
        "bascula_bebe",
        "camilla_radiotransp",
        "cardiotocografo",
        "carro_rojo_reanim",
        "cuna_calor_rad",
        "cuna_calor_rad_foto",
        "defibrilador_monit",
        "ecocardiografo",
        "electrocardiografo",
        "estuche_diag",
        "incubadora_fototer",
        "incubadora_trasl",
        "incubadora_cuidados",
        "lampara_quirurgica_doble",
        "lampara_quir_port",
        "lampara_quir_senc",
        "mesa_quir_obs",
        "mesa_exploracion",
        "mesa_quir_gral",
        "microscopio_rutina",
        "monitor_radiacion",
        "monitor_signos_vit_avanz",
        "monitor_signos_neo",
        "monitor_signos_bas",
        "monitor_traslado",
        "monitor_signos_int",
        "monitor_signos_vit_neona",
        "monitor_anestesia",
        "negatoscopio",
        "refrige_lab",
        "sierra_yesos",
        "ultrasonido_diag",
        "unidad_anestesia_bas",
        "ultrasonido_terap",
        "unidad_dental",
        "unidad_rx_analogo",
        "unidad_rx_dental",
        "unidad_rx_digital",
        "unidad_rx_port_ana",
        "unidad_rx_port_dig",
        "fluoroscopio_dig",
        "fluoroscopio_dig_analog",
        "mastografo_digital",
        "mastografo_estereo",
        "mastografo_estereo_tomosin",
        "microscopio_cirugia",
        "resonancia_mag",
        "tomografo_128",
        "tomografo_16",
        "tomografo_32",
        "tomografo_64",
        }

   
    # ==========================================================
    # PARAMETROS
    # ==========================================================

    # Leer parámetros con soporte fallback
    unidades = (
        request.args.getlist("clues[]")
        or request.args.getlist("unidades[]")
        or request.args.getlist("clues")
    )

    anios_raw = request.args.getlist("anios[]") or request.args.getlist("anios")
    meses_raw = request.args.getlist("meses[]") or request.args.getlist("meses")

    indicadores_solicitados = (
        request.args.getlist("indicadores[]")
        or request.args.getlist("indicadores")
    )
    indicadores_solicitados = [i.strip().lower() for i in indicadores_solicitados]

    tipologia = request.args.get("tipologia", "TODAS")
    modo_agrupacion = request.args.get("modo", "acumulado")

    # Normalizar numéricos
    anios = [int(a) for a in anios_raw if str(a).isdigit()]
    meses = [int(m) for m in meses_raw if str(m).isdigit()]

    # Si seleccionan los 12 meses, si viene el mes 13, o si no seleccionan ninguno, es vista ANUAL/ACUMULADA
    meses_validos = [m for m in meses if m != 13]
    quiere_anual = (13 in meses) or (len(meses) == 0)
    es_anual = quiere_anual

    if not meses_validos:
        meses_validos = list(range(1, 13))

    meses_calculo = meses_validos

    # ==========================================================
    # FLAGS DE EJECUCIÓN
    # ==========================================================

    es_descarga_masiva = len(indicadores_solicitados) == 0

    quiere_kpis = es_descarga_masiva or any(
        i in kpis_calculados
        or i in indicadores_equipo_medico
        for i in indicadores_solicitados
    )

    quiere_vistas = es_descarga_masiva or any(
        i not in kpis_calculados for i in indicadores_solicitados
    )

    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    data_acumulada = []

    # PARTE 3
    # ==========================================================
    # CONFIGURACIÓN BASE DE GROUP BY
    # ==========================================================

    es_acumulado = (modo_agrupacion != "individual" and len(unidades) > 1)

    if es_acumulado:
        group_by_cols = ["e.anio"]
        select_unidad = "'TOTAL' AS clues, 'TOTAL GRUPO' AS nombre_unidad, 'TODAS' AS tipologia,"
    else:
        group_by_cols = ["e.anio", "e.clues", "e.nombre_unidad", "c.tipologia"]
        select_unidad = "e.clues, e.nombre_unidad, c.tipologia,"

    if not quiere_anual:
        group_by_cols.append("e.mes")

    group_by = ",\n".join(group_by_cols)
    select_mes = "e.mes," if not quiere_anual else "13 AS mes,"

    agg_camas = "AVG" if quiere_anual else "MAX"

    # ==========================================================
    # KPIS
    # ==========================================================

    rows_e = []

    if quiere_kpis:

        where_e = "WHERE 1=1"
        params_e = []

        if unidades:
            where_e += " AND e.clues IN ({})".format(",".join(["%s"] * len(unidades)))
            params_e.extend(unidades)

        if anios:
            where_e += " AND e.anio IN ({})".format(",".join(["%s"] * len(anios)))
            params_e.extend(anios)

        if meses_calculo:
            where_e += " AND e.mes IN ({})".format(",".join(["%s"] * len(meses_calculo)))
            params_e.extend(meses_calculo)

        # Solo filtramos tipología si NO estamos consolidando todo el grupo
        if tipologia != "TODAS" and not es_acumulado:
            where_e += " AND c.tipologia = %s"
            params_e.append(tipologia)

        # ======================================================
        # QUERY PRINCIPAL
        # ======================================================

        query_e = f"""
                SELECT 
                    e.anio,
                    {select_mes}
                    {select_unidad}

                    -- EGRESOS Y NACIMIENTOS (TABLA PRINCIPAL)
                    SUM(e.total_egresos) AS total_egresos,        
                    SUM(e.defunciones) AS egre_defunciones,
                    SUM(e.defunciones_48h) AS egre_defunciones_48h,
                    SUM(e.dias_estancia_sum) AS dias_estancia,
                    SUM(e.dias_estancia_med_interna) AS dias_est_med,
                    SUM(e.dias_estancia_cirugia) AS dias_est_cir,
                    SUM(e.dias_estancia_pediatria) AS dias_est_ped,
                    SUM(e.dias_estancia_ginecobstetricia) AS dias_est_gin,
                    SUM(e.dias_estancia_otros) AS dias_est_otros,
                    SUM(e.nacimientos) AS total_nacimientos,
                    SUM(e.nac_distocico) AS nac_distocico,
                    SUM(e.nac_eutocico) AS nac_eutocico,
                    SUM(e.cesareas) AS nac_cesarea,
                    SUM(e.apeo) AS apeo,
                    SUM(e.abortos) AS abortos,
                    SUM(e.abortos + e.nacimientos) AS eventos_obstetricos,
                    SUM(e.apeo) AS total_apeo,
                    
                    SUM(e.med_interna) AS egre_med_interna,
                    SUM(e.cirugia) AS egre_cirugia,
                    SUM(e.pediatria) AS egre_pediatria,
                    SUM(e.ginecobstetricia) AS egre_gineco,
                    SUM(e.otros) AS egre_otros,

                    -- EGRESOS >48H POR SERVICIO
                    SUM(e.egresos_med_interna_48h) AS egre_med_int_48h,
                    SUM(e.egresos_cirugia_48h) AS egre_cirugia_48h,
                    SUM(e.egresos_pediatria_48h) AS egre_pediatria_48h,
                    SUM(e.egresos_ginecobstetricia_48h) AS egre_gineco_48h,
                    SUM(e.egresos_otros_48h) AS egre_otros_48h,
                    SUM(e.egresos_48h) AS total_egresos_48h,

                    -- DETALLE ABORTOS
                    SUM(IFNULL(ab.abortos_lui, 0)) AS abortos_lui,
                    SUM(IFNULL(ab.abortos_ameu, 0)) AS abortos_ameu,
                    SUM(IFNULL(ab.abortos_medicado, 0)) AS abortos_medicado,
                    SUM(IFNULL(ab.abortos_no_especificado, 0)) AS abortos_no_especificado,
                    SUM(IFNULL(ab.abortos_total, 0)) AS abortos_total,

                    -- SIS (SERVICIOS DE SALUD)
                    SUM(IFNULL(sis.dias_p, 0)) AS dias_p,
                    SUM(IFNULL(sis.consultas, 0)) AS consultas,
                    SUM(IFNULL(sis.especialidad, 0)) AS especialidad,
                    SUM(IFNULL(sis.mental, 0)) AS mental,
                    SUM(IFNULL(sis.bucal, 0)) AS bucal,
                    SUM(IFNULL(sis.laboratorio, 0)) AS laboratorio,
                    SUM(IFNULL(sis.rayosx, 0)) AS rayosx,
                    SUM(IFNULL(sis.anatomia, 0)) AS anatomia,
                    SUM(IFNULL(sis.electro, 0)) AS electro,
                    SUM(IFNULL(sis.encefa, 0)) AS encefa,
                    SUM(IFNULL(sis.ultrasonido, 0)) AS ultrasonido,
                    SUM(IFNULL(sis.tac, 0)) AS tac,
                    SUM(IFNULL(sis.rnm, 0)) AS rnm,
                    SUM(IFNULL(sis.med_interna, 0)) AS dias_p_med_int,
                    SUM(IFNULL(sis.cirugia, 0)) AS dias_p_cirugia,
                    SUM(IFNULL(sis.gineco, 0)) AS dias_p_gineco,
                    SUM(IFNULL(sis.pediatria, 0)) AS dias_p_pediatria,
                    SUM(IFNULL(sis.otros, 0)) AS dias_p_otros,

                    -- URGENCIAS
                    SUM(IFNULL(urg.total_u, 0)) AS urgencias,
                    SUM(IFNULL(urg.calificada, 0)) AS calificada,
                    SUM(IFNULL(urg.no_calificada, 0)) AS no_calificada,
                    SUM(IFNULL(urg.medica, 0)) AS medica,
                    SUM(IFNULL(urg.accidentes, 0)) AS accidentes,
                    SUM(IFNULL(urg.pediatrica, 0)) AS pediatrica,
                    SUM(IFNULL(urg.ginecobstetricia, 0)) AS ginecobstetricia,

                    -- PROCEDIMIENTOS DENTRO DE QUIRÓFANO
                    SUM(IFNULL(p.med_int_dentro, 0)) AS med_int_dentro,
                    SUM(IFNULL(p.cirugia_dentro, 0)) AS cirugia_dentro,
                    SUM(IFNULL(p.gineco_dentro, 0)) AS gineco_dentro,
                    SUM(IFNULL(p.pediatria_dentro, 0)) AS pediatria_dentro,
                    SUM(IFNULL(p.otros_dentro, 0)) AS otros_dentro,
                    SUM(IFNULL(p.total_proced_dentro, 0)) AS total_proced_dentro,

                    -- PROCEDIMIENTOS FUERA DE QUIRÓFANO
                    SUM(IFNULL(p.med_int_fuera, 0)) AS med_int_fuera,
                    SUM(IFNULL(p.cirugia_fuera, 0)) AS cirugia_fuera,
                    SUM(IFNULL(p.gineco_fuera, 0)) AS gineco_fuera,
                    SUM(IFNULL(p.pediatria_fuera, 0)) AS pediatria_fuera,
                    SUM(IFNULL(p.otros_fuera, 0)) AS otros_fuera,
                    SUM(IFNULL(p.total_proced_fuera, 0)) AS total_proced_fuera,

                    -- TOTAL PROCEDIMIENTOS
                    SUM(IFNULL(p.total_proced_med_int, 0)) AS total_proced_med_int,
                    SUM(IFNULL(p.total_proced_cirugia, 0)) AS total_proced_cirugia,
                    SUM(IFNULL(p.total_proced_gineco, 0)) AS total_proced_gineco,
                    SUM(IFNULL(p.total_proced_pediatria, 0)) AS total_proced_pediatria,
                    SUM(IFNULL(p.total_proced_otros, 0)) AS total_proced_otros,
                    SUM(IFNULL(p.total_proced, 0)) AS total_proced,

                    -- ADOLESCENTES
                    SUM(e.adolescente_apeo) AS adolescente_apeo,
                    SUM(e.eventos_obstetricos_adolescentes) AS eventos_obstetricos_adolescentes,

                    -- RECURSOS FISICOS (KPIs)
                    SUM(IFNULL(p.total_proced_dentro, 0)) AS cirugias,
                    {agg_camas}(IFNULL(sin.camas_total, 0)) AS camas_total,
                    {agg_camas}(IFNULL(sin.quirofanos, 0)) AS quirofanos,
                    {agg_camas}(IFNULL(sin.camas_med_int, 0)) AS camas_med_int,
                    {agg_camas}(IFNULL(sin.camas_cirugia, 0)) AS camas_cirugia,
                    {agg_camas}(IFNULL(sin.camas_gineco, 0)) AS camas_gineco,
                    {agg_camas}(IFNULL(sin.camas_pediatria, 0)) AS camas_pediatria,
                    {agg_camas}(IFNULL(sin.camas_otros, 0)) AS camas_otros,

                    -- DÍAS CAMA
                    SUM(IFNULL(sin.camas_total,0) * DAY(LAST_DAY(CONCAT(e.anio,'-',LPAD(e.mes,2,'0'),'-01')))) AS dias_cama_total,
                    SUM(IFNULL(sin.camas_med_int,0) * DAY(LAST_DAY(CONCAT(e.anio,'-',LPAD(e.mes,2,'0'),'-01')))) AS dias_cama_med,
                    SUM(IFNULL(sin.camas_cirugia,0) * DAY(LAST_DAY(CONCAT(e.anio,'-',LPAD(e.mes,2,'0'),'-01')))) AS dias_cama_cir,
                    SUM(IFNULL(sin.camas_gineco,0) * DAY(LAST_DAY(CONCAT(e.anio,'-',LPAD(e.mes,2,'0'),'-01')))) AS dias_cama_gin,
                    SUM(IFNULL(sin.camas_pediatria,0) * DAY(LAST_DAY(CONCAT(e.anio,'-',LPAD(e.mes,2,'0'),'-01')))) AS dias_cama_ped,
                    SUM(IFNULL(sin.camas_otros,0) * DAY(LAST_DAY(CONCAT(e.anio,'-',LPAD(e.mes,2,'0'),'-01')))) AS dias_cama_otros,

                    -- CAMAS NO CENSABLES
                    {agg_camas}(IFNULL(cnc.hab_urgencias, 0)) AS hab_urgencias,
                    {agg_camas}(IFNULL(cnc.hab_observacion, 0)) AS hab_observacion,
                    {agg_camas}(IFNULL(cnc.hab_cuid_int, 0)) AS hab_cuid_int,
                    {agg_camas}(IFNULL(cnc.hab_cirug_amb, 0)) AS hab_cirug_amb,
                    {agg_camas}(IFNULL(cnc.hab_quemados, 0)) AS hab_quemados,
                    {agg_camas}(IFNULL(cnc.hab_lab_parto, 0)) AS hab_lab_parto,
                    {agg_camas}(IFNULL(cnc.hab_recup_pp, 0)) AS hab_recup_pp,
                    {agg_camas}(IFNULL(cnc.hab_recup_pq, 0)) AS hab_recup_pq,
                    {agg_camas}(IFNULL(cnc.hab_uci_adulto, 0)) AS hab_uci_adulto,
                    {agg_camas}(IFNULL(cnc.hab_uci_ped, 0)) AS hab_uci_ped,
                    {agg_camas}(IFNULL(cnc.hab_otras_areas, 0)) AS hab_otras_areas,
                    MAX(IFNULL(cnc.total_no_censables, 0)) AS total_no_censables,

                    -- EQUIPO MÉDICO
                    {agg_camas}(IFNULL(em.arco_c_analogo, 0)) AS arco_c_analogo,
                    {agg_camas}(IFNULL(em.arco_c_digital, 0)) AS arco_c_digital,
                    {agg_camas}(IFNULL(em.bascula_estadimetro, 0)) AS bascula_estadimetro,
                    {agg_camas}(IFNULL(em.bascula_bebe, 0)) AS bascula_bebe,
                    {agg_camas}(IFNULL(em.camilla_radiotransp, 0)) AS camilla_radiotransp,
                    {agg_camas}(IFNULL(em.cardiotocografo, 0)) AS cardiotocografo,
                    {agg_camas}(IFNULL(em.carro_rojo_reanim, 0)) AS carro_rojo_reanim,
                    {agg_camas}(IFNULL(em.cuna_calor_rad, 0)) AS cuna_calor_rad,
                    {agg_camas}(IFNULL(em.cuna_calor_rad_foto, 0)) AS cuna_calor_rad_foto,
                    {agg_camas}(IFNULL(em.defibrilador_monit, 0)) AS defibrilador_monit,
                    {agg_camas}(IFNULL(em.ecocardiografo, 0)) AS ecocardiografo,
                    {agg_camas}(IFNULL(em.electrocardiografo, 0)) AS electrocardiografo,
                    {agg_camas}(IFNULL(em.estuche_diag, 0)) AS estuche_diag,
                    {agg_camas}(IFNULL(em.incubadora_fototer, 0)) AS incubadora_fototer,
                    {agg_camas}(IFNULL(em.incubadora_trasl, 0)) AS incubadora_trasl,
                    {agg_camas}(IFNULL(em.incubadora_cuidados, 0)) AS incubadora_cuidados,
                    {agg_camas}(IFNULL(em.lampara_quirurgica_doble, 0)) AS lampara_quirurgica_doble,
                    {agg_camas}(IFNULL(em.lampara_quir_port, 0)) AS lampara_quir_port,
                    {agg_camas}(IFNULL(em.lampara_quir_senc, 0)) AS lampara_quir_senc,
                    {agg_camas}(IFNULL(em.mesa_quir_obs, 0)) AS mesa_quir_obs,
                    {agg_camas}(IFNULL(em.mesa_exploracion, 0)) AS mesa_exploracion,
                    {agg_camas}(IFNULL(em.mesa_quir_gral, 0)) AS mesa_quir_gral,
                    {agg_camas}(IFNULL(em.microscopio_rutina, 0)) AS microscopio_rutina,
                    {agg_camas}(IFNULL(em.monitor_radiacion, 0)) AS monitor_radiacion,
                    {agg_camas}(IFNULL(em.monitor_signos_vit_avanz, 0)) AS monitor_signos_vit_avanz,
                    {agg_camas}(IFNULL(em.monitor_signos_neo, 0)) AS monitor_signos_neo,
                    {agg_camas}(IFNULL(em.monitor_signos_bas, 0)) AS monitor_signos_bas,
                    {agg_camas}(IFNULL(em.monitor_traslado, 0)) AS monitor_traslado,
                    {agg_camas}(IFNULL(em.monitor_signos_int, 0)) AS monitor_signos_int,
                    {agg_camas}(IFNULL(em.monitor_signos_vit_neona, 0)) AS monitor_signos_vit_neona,
                    {agg_camas}(IFNULL(em.monitor_anestesia, 0)) AS monitor_anestesia,
                    {agg_camas}(IFNULL(em.negatoscopio, 0)) AS negatoscopio,
                    {agg_camas}(IFNULL(em.refrige_lab, 0)) AS refrige_lab,
                    {agg_camas}(IFNULL(em.sierra_yesos, 0)) AS sierra_yesos,
                    {agg_camas}(IFNULL(em.ultrasonido_diag, 0)) AS ultrasonido_diag,
                    {agg_camas}(IFNULL(em.unidad_anestesia_bas, 0)) AS unidad_anestesia_bas,
                    {agg_camas}(IFNULL(em.ultrasonido_terap, 0)) AS ultrasonido_terap,
                    {agg_camas}(IFNULL(em.unidad_dental, 0)) AS unidad_dental,
                    {agg_camas}(IFNULL(em.unidad_rx_analogo, 0)) AS unidad_rx_analogo,
                    {agg_camas}(IFNULL(em.unidad_rx_dental, 0)) AS unidad_rx_dental,
                    {agg_camas}(IFNULL(em.unidad_rx_digital, 0)) AS unidad_rx_digital,
                    {agg_camas}(IFNULL(em.unidad_rx_port_ana, 0)) AS unidad_rx_port_ana,
                    {agg_camas}(IFNULL(em.unidad_rx_port_dig, 0)) AS unidad_rx_port_dig,
                    {agg_camas}(IFNULL(em.fluoroscopio_dig, 0)) AS fluoroscopio_dig,
                    {agg_camas}(IFNULL(em.fluoroscopio_dig_analog, 0)) AS fluoroscopio_dig_analog,
                    {agg_camas}(IFNULL(em.mastografo_digital, 0)) AS mastografo_digital,
                    {agg_camas}(IFNULL(em.mastografo_estereo, 0)) AS mastografo_estereo,
                    {agg_camas}(IFNULL(em.mastografo_estereo_tomosin, 0)) AS mastografo_estereo_tomosin,
                    {agg_camas}(IFNULL(em.microscopio_cirugia, 0)) AS microscopio_cirugia,
                    {agg_camas}(IFNULL(em.resonancia_mag, 0)) AS resonancia_mag,
                    {agg_camas}(IFNULL(em.tomografo_128, 0)) AS tomografo_128,
                    {agg_camas}(IFNULL(em.tomografo_16, 0)) AS tomografo_16,
                    {agg_camas}(IFNULL(em.tomografo_32, 0)) AS tomografo_32,
                    {agg_camas}(IFNULL(em.tomografo_64, 0)) AS tomografo_64

                FROM egresos_agregado e

                -- JOIN CATALOGO UNIDADES
                LEFT JOIN catalogo_unidades c ON e.clues = c.clues

                -- JOIN ABORTOS
                LEFT JOIN (
                    SELECT anio, mes, clues,
                        SUM(lui) AS abortos_lui, SUM(ameu) AS abortos_ameu,
                        SUM(medicamento) AS abortos_medicado, SUM(no_especificado) AS abortos_no_especificado,
                        SUM(total) AS abortos_total
                    FROM abortos GROUP BY anio, mes, clues
                ) ab ON e.clues = ab.clues AND e.anio = ab.anio AND e.mes = ab.mes

                -- JOIN SIS
                LEFT JOIN (
                    SELECT anio, mes, clues,
                        SUM(diasPaciente) AS dias_p, SUM(consultas) AS consultas,
                        SUM(especialidad) AS especialidad, SUM(mental) AS mental,
                        SUM(bucal) AS bucal, SUM(laboratorio) AS laboratorio,
                        SUM(rayosx) AS rayosx, SUM(anatomia) AS anatomia,
                        SUM(electro) AS electro, SUM(encefa) AS encefa,
                        SUM(ultrasonido) AS ultrasonido, SUM(tac) AS tac,
                        SUM(rnm) AS rnm, SUM(med_interna) AS med_interna,
                        SUM(cirugia) AS cirugia, SUM(gineco) AS gineco,
                        SUM(pediatria) AS pediatria, SUM(otros) AS otros
                    FROM sis_registros_agregados GROUP BY anio, mes, clues
                ) sis ON e.clues = sis.clues AND e.anio = sis.anio AND e.mes = sis.mes

                -- JOIN URGENCIAS
                LEFT JOIN (
                    SELECT anio, mes_estadistico, clues,
                        SUM(total) AS total_u, SUM(calificada) AS calificada,
                        SUM(no_calificada) AS no_calificada, SUM(medica) AS medica,
                        SUM(accidentes) AS accidentes, SUM(pediatrica) AS pediatrica,
                        SUM(ginecobstetricia) AS ginecobstetricia
                    FROM urgencias_agregado GROUP BY anio, mes_estadistico, clues
                ) urg ON e.clues = urg.clues AND e.anio = urg.anio AND e.mes = urg.mes_estadistico

                -- JOIN PROCEDIMIENTOS
                LEFT JOIN (
                    SELECT anio, mes, clues,
                        SUM(med_int_proced_dentro) AS med_int_dentro,
                        SUM(cirugia_proced_dentro) AS cirugia_dentro,
                        SUM(gineco_proced_dentro) AS gineco_dentro,
                        SUM(pediatra_proced_dentro) AS pediatria_dentro,
                        SUM(otros_proced_dentro) AS otros_dentro,
                        SUM(total_proced_dentro) AS total_proced_dentro,
                        SUM(med_int_proced_fuera) AS med_int_fuera,
                        SUM(cirugia_proced_fuera) AS cirugia_fuera,
                        SUM(gineco_proced_fuera) AS gineco_fuera,
                        SUM(pediatra_proced_fuera) AS pediatria_fuera,
                        SUM(otros_proced_fuera) AS otros_fuera,
                        SUM(total_proced_fuera) AS total_proced_fuera,
                        SUM(IFNULL(med_int_proced_dentro,0) + IFNULL(med_int_proced_fuera,0)) AS total_proced_med_int,
                        SUM(IFNULL(cirugia_proced_dentro,0) + IFNULL(cirugia_proced_fuera,0)) AS total_proced_cirugia,
                        SUM(IFNULL(gineco_proced_dentro,0) + IFNULL(gineco_proced_fuera,0)) AS total_proced_gineco,
                        SUM(IFNULL(pediatra_proced_dentro,0) + IFNULL(pediatra_proced_fuera,0)) AS total_proced_pediatria,
                        SUM(IFNULL(otros_proced_dentro,0) + IFNULL(otros_proced_fuera,0)) AS total_proced_otros,
                        SUM(IFNULL(total_proced_dentro,0) + IFNULL(total_proced_fuera,0)) AS total_proced
                    FROM procedimiento_agregado GROUP BY anio, mes, clues
                ) p ON e.clues = p.clues AND e.anio = p.anio AND e.mes = p.mes

                -- JOIN SINERHIAS (AGRUPADO)
                LEFT JOIN (
                    SELECT anio, mes, clues,
                        AVG(IFNULL(total, 0)) AS camas_total,
                        AVG(IFNULL(quirofanos, 0)) AS quirofanos,
                        AVG(IFNULL(med_int, 0)) AS camas_med_int,
                        AVG(IFNULL(cirugia, 0)) AS camas_cirugia,
                        AVG(IFNULL(gineco, 0)) AS camas_gineco,
                        AVG(IFNULL(pediatria, 0)) AS camas_pediatria,
                        AVG(IFNULL(otros, 0)) AS camas_otros
                    FROM sinerhias GROUP BY anio, mes, clues
                ) sin ON e.clues = sin.clues AND e.anio = sin.anio AND e.mes = sin.mes

                -- JOIN CAMAS NO CENSABLES (AGRUPADO)
                LEFT JOIN (
                    SELECT anio, mes, clues,
                        SUM(IFNULL(hab_urgencias, 0)) AS hab_urgencias,
                        SUM(IFNULL(hab_observacion, 0)) AS hab_observacion,
                        SUM(IFNULL(hab_cuid_int, 0)) AS hab_cuid_int,
                        SUM(IFNULL(hab_cirug_amb, 0)) AS hab_cirug_amb,
                        SUM(IFNULL(hab_quemados, 0)) AS hab_quemados,
                        SUM(IFNULL(hab_lab_parto, 0)) AS hab_lab_parto,
                        SUM(IFNULL(hab_recup_pp, 0)) AS hab_recup_pp,
                        SUM(IFNULL(hab_recup_pq, 0)) AS hab_recup_pq,
                        SUM(IFNULL(hab_uci_adulto, 0)) AS hab_uci_adulto,
                        SUM(IFNULL(hab_uci_ped, 0)) AS hab_uci_ped,
                        SUM(IFNULL(hab_otras_areas, 0)) AS hab_otras_areas,
                        SUM(
                            IFNULL(hab_urgencias, 0) + IFNULL(hab_observacion, 0) +
                            IFNULL(hab_cuid_int, 0) + IFNULL(hab_cirug_amb, 0) +
                            IFNULL(hab_quemados, 0) + IFNULL(hab_lab_parto, 0) +
                            IFNULL(hab_recup_pp, 0) + IFNULL(hab_recup_pq, 0) +
                            IFNULL(hab_uci_adulto, 0) + IFNULL(hab_uci_ped, 0) +
                            IFNULL(hab_otras_areas, 0)
                        ) AS total_no_censables
                    FROM camas_no_censables GROUP BY anio, mes, clues
                ) cnc ON e.clues = cnc.clues AND e.anio = cnc.anio AND e.mes = cnc.mes

                -- JOIN EQUIPO MÉDICO (AGRUPADO)
                LEFT JOIN (
                    SELECT anio, mes, clues,
                        SUM(IFNULL(arco_c_analogo, 0)) AS arco_c_analogo,
                        SUM(IFNULL(arco_c_digital, 0)) AS arco_c_digital,
                        SUM(IFNULL(bascula_estadimetro, 0)) AS bascula_estadimetro,
                        SUM(IFNULL(bascula_bebe, 0)) AS bascula_bebe,
                        SUM(IFNULL(camilla_radiotransp, 0)) AS camilla_radiotransp,
                        SUM(IFNULL(cardiotocografo, 0)) AS cardiotocografo,
                        SUM(IFNULL(carro_rojo_reanim, 0)) AS carro_rojo_reanim,
                        SUM(IFNULL(cuna_calor_rad, 0)) AS cuna_calor_rad,
                        SUM(IFNULL(cuna_calor_rad_foto, 0)) AS cuna_calor_rad_foto,
                        SUM(IFNULL(defibrilador_monit, 0)) AS defibrilador_monit,
                        SUM(IFNULL(ecocardiografo, 0)) AS ecocardiografo,
                        SUM(IFNULL(electrocardiografo, 0)) AS electrocardiografo,
                        SUM(IFNULL(estuche_diag, 0)) AS estuche_diag,
                        SUM(IFNULL(incubadora_fototer, 0)) AS incubadora_fototer,
                        SUM(IFNULL(incubadora_trasl, 0)) AS incubadora_trasl,
                        SUM(IFNULL(incubadora_cuidados, 0)) AS incubadora_cuidados,
                        SUM(IFNULL(lampara_quirurgica_doble, 0)) AS lampara_quirurgica_doble,
                        SUM(IFNULL(lampara_quir_port, 0)) AS lampara_quir_port,
                        SUM(IFNULL(lampara_quir_senc, 0)) AS lampara_quir_senc,
                        SUM(IFNULL(mesa_quir_obs, 0)) AS mesa_quir_obs,
                        SUM(IFNULL(mesa_exploracion, 0)) AS mesa_exploracion,
                        SUM(IFNULL(mesa_quir_gral, 0)) AS mesa_quir_gral,
                        SUM(IFNULL(microscopio_rutina, 0)) AS microscopio_rutina,
                        SUM(IFNULL(monitor_radiacion, 0)) AS monitor_radiacion,
                        SUM(IFNULL(monitor_signos_vit_avanz, 0)) AS monitor_signos_vit_avanz,
                        SUM(IFNULL(monitor_signos_neo, 0)) AS monitor_signos_neo,
                        SUM(IFNULL(monitor_signos_bas, 0)) AS monitor_signos_bas,
                        SUM(IFNULL(monitor_traslado, 0)) AS monitor_traslado,
                        SUM(IFNULL(monitor_signos_int, 0)) AS monitor_signos_int,
                        SUM(IFNULL(monitor_signos_vit_neona, 0)) AS monitor_signos_vit_neona,
                        SUM(IFNULL(monitor_anestesia, 0)) AS monitor_anestesia,
                        SUM(IFNULL(negatoscopio, 0)) AS negatoscopio,
                        SUM(IFNULL(refrige_lab, 0)) AS refrige_lab,
                        SUM(IFNULL(sierra_yesos, 0)) AS sierra_yesos,
                        SUM(IFNULL(ultrasonido_diag, 0)) AS ultrasonido_diag,
                        SUM(IFNULL(unidad_anestesia_bas, 0)) AS unidad_anestesia_bas,
                        SUM(IFNULL(ultrasonido_terap, 0)) AS ultrasonido_terap,
                        SUM(IFNULL(unidad_dental, 0)) AS unidad_dental,
                        SUM(IFNULL(unidad_rx_analogo, 0)) AS unidad_rx_analogo,
                        SUM(IFNULL(unidad_rx_dental, 0)) AS unidad_rx_dental,
                        SUM(IFNULL(unidad_rx_digital, 0)) AS unidad_rx_digital,
                        SUM(IFNULL(unidad_rx_port_ana, 0)) AS unidad_rx_port_ana,
                        SUM(IFNULL(unidad_rx_port_dig, 0)) AS unidad_rx_port_dig,
                        SUM(IFNULL(fluoroscopio_dig, 0)) AS fluoroscopio_dig,
                        SUM(IFNULL(fluoroscopio_dig_analog, 0)) AS fluoroscopio_dig_analog,
                        SUM(IFNULL(mastografo_digital, 0)) AS mastografo_digital,
                        SUM(IFNULL(mastografo_estereo, 0)) AS mastografo_estereo,
                        SUM(IFNULL(mastografo_estereo_tomosin, 0)) AS mastografo_estereo_tomosin,
                        SUM(IFNULL(microscopio_cirugia, 0)) AS microscopio_cirugia,
                        SUM(IFNULL(resonancia_mag, 0)) AS resonancia_mag,
                        SUM(IFNULL(tomografo_128, 0)) AS tomografo_128,
                        SUM(IFNULL(tomografo_16, 0)) AS tomografo_16,
                        SUM(IFNULL(tomografo_32, 0)) AS tomografo_32,
                        SUM(IFNULL(tomografo_64, 0)) AS tomografo_64
                    FROM equipo_medico GROUP BY anio, mes, clues
                ) em ON e.clues = em.clues AND e.anio = em.anio AND e.mes = em.mes

                {where_e}

                GROUP BY {group_by}
                """

        try:
            cur.execute(query_e, params_e)
            rows_e = cur.fetchall()
        except Exception as err:
            import traceback
            traceback.print_exc()
            return jsonify({"error": str(err), "detalles": "Fallo al ejecutar la consulta en MySQL"}), 500

        #PARTE 4
        # ==========================================================
        # CAMPOS EQUIPO MEDICO
        # ==========================================================

        cols_equipo_medico = [
            "arco_c_analogo",
            "arco_c_digital",
            "bascula_estadimetro",
            "bascula_bebe",
            "camilla_radiotransp",
            "cardiotocografo",
            "carro_rojo_reanim",
            "cuna_calor_rad",
            "cuna_calor_rad_foto",
            "defibrilador_monit",
            "ecocardiografo",
            "electrocardiografo",
            "estuche_diag",
            "incubadora_fototer",
            "incubadora_trasl",
            "incubadora_cuidados",
            "lampara_quirurgica_doble",
            "lampara_quir_port",
            "lampara_quir_senc",
            "mesa_quir_obs",
            "mesa_exploracion",
            "mesa_quir_gral",
            "microscopio_rutina",
            "monitor_radiacion",
            "monitor_signos_vit_avanz",
            "monitor_signos_neo",
            "monitor_signos_bas",
            "monitor_traslado",
            "monitor_signos_int",
            "monitor_signos_vit_neona",
            "monitor_anestesia",
            "negatoscopio",
            "refrige_lab",
            "sierra_yesos",
            "ultrasonido_diag",
            "unidad_anestesia_bas",
            "ultrasonido_terap",
            "unidad_dental",
            "unidad_rx_analogo",
            "unidad_rx_dental",
            "unidad_rx_digital",
            "unidad_rx_port_ana",
            "unidad_rx_port_dig",
            "fluoroscopio_dig",
            "fluoroscopio_dig_analog",
            "mastografo_digital",
            "mastografo_estereo",
            "mastografo_estereo_tomosin",
            "microscopio_cirugia",
            "resonancia_mag",
            "tomografo_128",
            "tomografo_16",
            "tomografo_32",
            "tomografo_64",
        ]

        indicadores_max = {
            "camas_cirugia",
            "camas_gineco",
            "camas_med_int",
            "camas_otros",
            "camas_pediatria",
            "camas_total",
            "quirofanos",
            "hab_cirug_amb",
            "hab_cuid_int",
            "hab_lab_parto",
            "hab_observacion",
            "hab_otras_areas",
            "hab_quemados",
            "hab_recup_pp",
            "hab_recup_pq",
            "hab_uci_adulto",
            "hab_uci_ped",
            "hab_urgencias",
            }

       

             
        # ==========================================================
        # FUNCIONES ROBUSTAS (SIN KEYERROR)
        # ==========================================================
        def f(value):
            if value is None:
                return 0.0
            try:
                return float(value)
            except (ValueError, TypeError):
                return 0.0

        def calcular_ocupacion(dias_paciente, dias_cama):
            dp = f(dias_paciente)
            dc = f(dias_cama)
            return (dp / dc) * 100 if dc > 0 else 0.0

        def calcular_kpis(data, dias):
            # Usar .get() para evitar KeyError si la columna no existe en 'data'
            egresos = f(data.get("total_egresos"))
            camas = f(data.get("camas_total"))
            quirofanos = f(data.get("quirofanos"))
            
            nacimientos = f(data.get("total_nacimientos"))
            abortos = f(data.get("abortos"))
            eventos = nacimientos + abortos

            adolescente_apeo = f(data.get("adolescente_apeo"))
            eventos_obstetricos_adolescentes = f(data.get("eventos_obstetricos_adolescentes"))

            dias_est_med = f(data.get("dias_est_med"))
            dias_est_cir = f(data.get("dias_est_cir"))
            dias_est_ped = f(data.get("dias_est_ped"))
            dias_est_gin = f(data.get("dias_est_gin"))
            dias_est_otr = f(data.get("dias_est_otros"))

            egresos_med = f(data.get("egre_med_interna"))
            egresos_cir = f(data.get("egre_cirugia"))
            egresos_ped = f(data.get("egre_pediatria"))
            egresos_gin = f(data.get("egre_gineco"))
            egresos_otr = f(data.get("egre_otros"))

            dias_val = float(dias) if dias else 30.0

            return {
                # KPIs Operativos
                "consultas_por_dia": f(data.get("consultas")) / dias_val if dias_val else 0,
                "especialidad_por_dia": f(data.get("especialidad")) / dias_val if dias_val else 0,
                "urgencias_por_dia": f(data.get("urgencias")) / dias_val if dias_val else 0,
                "porcentaje_calificada": (
                    (f(data.get("calificada")) / f(data.get("urgencias")) * 100)
                    if f(data.get("urgencias")) > 0
                    else 0
                ),
                "nacimientos_por_dia": nacimientos / dias_val if dias_val else 0,
                "porcentaje_cesareas": (
                    (f(data.get("nac_cesarea")) / nacimientos * 100) if nacimientos > 0 else 0
                ),
                "prom_inter_diarias_qx": (
                    round(f(data.get("total_proced_dentro")) / (quirofanos * dias_val), 2)
                    if quirofanos > 0 and dias_val > 0
                    else 0
                ),
                "porcentaje_apeo": (f(data.get("apeo")) / eventos * 100) if eventos > 0 else 0,
                "porcentaje_adolescente_apeo": (
                    (adolescente_apeo * 100) / eventos_obstetricos_adolescentes
                    if eventos_obstetricos_adolescentes > 0
                    else 0
                ),

                # Ocupación
                "porcentaje_ocupacion": calcular_ocupacion(
                    data.get("dias_p"), data.get("dias_cama_total")
                ),
                "porcentaje_ocupacion_med_interna": calcular_ocupacion(
                    data.get("dias_p_med_int"), data.get("dias_cama_med")
                ),
                "porcentaje_ocupacion_cirugia": calcular_ocupacion(
                    data.get("dias_p_cirugia"), data.get("dias_cama_cir")
                ),
                "porcentaje_ocupacion_pediatria": calcular_ocupacion(
                    data.get("dias_p_pediatria"), data.get("dias_cama_ped")
                ),
                "porcentaje_ocupacion_gineco": calcular_ocupacion(
                    data.get("dias_p_gineco"), data.get("dias_cama_gin")
                ),
                "porcentaje_ocupacion_otros": calcular_ocupacion(
                    data.get("dias_p_otros"), data.get("dias_cama_otros")
                ),

                # Estancia y Rotación
                "prom_dias_estancia": (
                    (f(data.get("dias_estancia")) / egresos) if egresos > 0 else 0
                ),
                "prom_estancia_med_interna": (dias_est_med / egresos_med) if egresos_med > 0 else 0,
                "prom_estancia_cirugia": (dias_est_cir / egresos_cir) if egresos_cir > 0 else 0,
                "prom_estancia_pediatria": (dias_est_ped / egresos_ped) if egresos_ped > 0 else 0,
                "prom_estancia_gineco": (dias_est_gin / egresos_gin) if egresos_gin > 0 else 0,
                "prom_estancia_otros": (dias_est_otr / egresos_otr) if egresos_otr > 0 else 0,

                "indice_rotacion": (egresos / camas) if camas > 0 else 0,
                "interv_sustitucion": (
                    (((camas * dias_val) - f(data.get("dias_p"))) / egresos) if egresos > 0 else 0
                ),

                # Mortalidad
                "mortalidad_cruda": (
                    (f(data.get("egre_defunciones")) * 1000 / egresos) if egresos > 0 else 0
                ),
                "mortalidad_ajustada": (
                    (f(data.get("egre_defunciones_48h")) * 1000 / f(data.get("total_egresos_48h")))
                    if f(data.get("total_egresos_48h")) > 0
                    else 0
                ),
            }
        
        #PARTE 5
        # ==========================================================
        # RECORRER ROWS
        # ==========================================================      

        for r in rows_e:

            anio = int(r["anio"])
            mes = int(r["mes"]) if r.get("mes") else 13
            unidad = r.get("nombre_unidad", "TOTAL GENERAL")
            clues_val = r.get("clues", "TOTAL")
            

            base = {
                field: float(r.get(field) or 0)
                for field in SUM_FIELDS + MAX_FIELDS
            }


            if mes != 13:
                dias = calendar.monthrange(anio, mes)[1]
            else:
                if meses_validos:
                    dias = sum(
                        calendar.monthrange(anio, m)[1]
                        for m in meses_validos
                    )
                else:
                    dias = 365

           

            kpis = calcular_kpis(base, dias)

            dataset = {**base, **kpis}

            for indicador, valor in dataset.items():

                indicador_norm = indicador.lower()

                if es_descarga_masiva or indicador_norm in indicadores_solicitados:

                    data_acumulada.append({
                        "anio": anio,
                        "mes": mes,
                        "clues": clues_val,
                        "nombre_unidad": unidad,
                        "tipologia": r.get("tipologia", "TODAS"),
                        "indicador": indicador_norm,
                        "valor": round(float(valor), 2),
                    })
    

    indicadores_ya_calculados = {field.lower() for field in SUM_FIELDS + MAX_FIELDS}

   

    if quiere_vistas:

       
        # ======================================================
        # QUERY BASE
        # ======================================================

        params_v = []

        query_v = """
        SELECT
            v.mes,
            v.indicador,
            v.anio,
            v.clues,
            COALESCE(c.nombre_unidad, v.nombre_unidad) AS nombre_unidad,
            COALESCE(c.tipologia, 'TODAS') AS tipologia,
            v.valor
        FROM vw_indicadores_unificados v
        LEFT JOIN catalogo_unidades c ON v.clues = c.clues
        WHERE 1=1
        """

        if unidades:
            query_v += " AND v.clues IN ({})".format(",".join(["%s"] * len(unidades)))
            params_v.extend(unidades)

        if anios:
            query_v += " AND v.anio IN ({})".format(",".join(["%s"] * len(anios)))
            params_v.extend(anios)

        if not es_descarga_masiva:

            solicitados_v = [
                i
                for i in indicadores_solicitados
                if i.lower() not in indicadores_ya_calculados
                and i not in kpis_calculados
            ]

            if solicitados_v:
                query_v += " AND v.indicador IN ({})".format(
                    ",".join(["%s"] * len(solicitados_v))
                )
                params_v.extend(solicitados_v)

        cur.execute(query_v, params_v)
        rows_v = cur.fetchall()

        # ======================================================
        # CACHE ANUAL
        # ======================================================

        vista_cache = {}

        for row in rows_v:

            mes = int(row["mes"])

            if meses_validos and mes not in meses_validos:
                continue

            indicador = row["indicador"].strip().lower()

            key = (
                row["anio"],
                row["clues"],
                row["nombre_unidad"],
                row["tipologia"],
                indicador,
            )

            valor = float(row["valor"] or 0)

            # ==================================================
            # ANUAL
            # ==================================================

            if es_anual:

                if key not in vista_cache:
                    vista_cache[key] = valor

                else:

                    if indicador in indicadores_max:
                        vista_cache[key] = max(vista_cache[key], valor)
                    else:
                        vista_cache[key] += valor

            # ==================================================
            # MENSUAL
            # ==================================================

            else:

                data_acumulada.append(
                    {
                        "anio": row["anio"],
                        "mes": mes,
                        "clues": row["clues"],
                        "nombre_unidad": row["nombre_unidad"],
                        "tipologia": row.get("tipologia", "TODAS"),
                        "indicador": indicador,
                        "valor": round(valor, 2),
                    }
                )

        # ======================================================
        # GENERAR MES 13
        # ======================================================

        if es_anual:

            for (anio, clues, unidad, tipologia, indicador), valor in vista_cache.items():

                if indicador in indicadores_ya_calculados:
                    continue

                data_acumulada.append(
                    {
                        "anio": anio,
                        "mes": 13,
                        "clues": clues,
                        "nombre_unidad": unidad,
                        "tipologia": tipologia,
                        "indicador": indicador,
                        "valor": round(valor, 2),
                    }
                )


    

            

    # PARTE 6
    # ==========================================================
    # TABLAS ESTÁTICAS (CAMAS NO CENSABLES Y EQUIPO MÉDICO)
    # ==========================================================
    cols_no_censables = [
        "hab_urgencias", "inh_urgencias", "tot_urgencias",
        "hab_observacion", "inh_observacion", "tot_observacion",
        "hab_cuid_int", "inh_cuid_int", "tot_cuid_int",
        "hab_cirug_amb", "inh_cirug_amb", "tot_cirug_amb",
        "hab_quemados", "inh_quemados", "tot_quemados",
        "hab_lab_parto", "inh_lab_parto", "tot_lab_parto",
        "hab_recup_pp", "inh_recup_pp", "tot_recup_pp",
        "hab_recup_pq", "inh_recup_pq", "tot_recup_pq",
        "hab_uci_adulto", "inh_uci_adulto", "tot_uci_adulto",
        "hab_uci_ped", "inh_uci_ped", "tot_uci_ped",
        "hab_otras_areas", "inh_otras_areas", "tot_otras_areas",
    ]

    procesar_tabla_estatica(
        tabla="camas_no_censables",
        alias="n",
        columnas=cols_no_censables,
        indicadores_solicitados=indicadores_solicitados,
        es_descarga_masiva=es_descarga_masiva,
        unidades=unidades,
        anios=anios,
        cur=cur,
        es_anual=es_anual,
        meses_validos=meses_validos,
        data_acumulada=data_acumulada,
    )

    procesar_tabla_estatica(
        tabla="equipo_medico",
        alias="em",
        columnas=cols_equipo_medico,
        indicadores_solicitados=indicadores_solicitados,
        es_descarga_masiva=es_descarga_masiva,
        unidades=unidades,
        anios=anios,
        cur=cur,
        es_anual=es_anual,
        meses_validos=meses_validos,
        data_acumulada=data_acumulada,
    )

    # ==========================================================
    # TOTAL GENERAL (SOLO SI HAY MÁS DE 1 UNIDAD)
    # ==========================================================
    if len(unidades) > 1 or modo_agrupacion == "acumulado":
        totales = generar_total_general(
            data_acumulada=data_acumulada,
            meses_validos=meses_validos,
            SUM_FIELDS=SUM_FIELDS,
            MAX_FIELDS=MAX_FIELDS,
            indicadores_max=indicadores_max,
            calcular_kpis=calcular_kpis,
            es_descarga_masiva=es_descarga_masiva,
            indicadores_solicitados=indicadores_solicitados,
        )
        if totales:
            data_acumulada.extend(totales)

    # ==========================================================
    # CIERRE Y ORDENAMIENTO SEGURO
    # ==========================================================
    cur.close()

    # Ordenamiento defensivo previniendo valores None
    data_acumulada.sort(
        key=lambda x: (
            x.get("anio") or 0,
            x.get("nombre_unidad") or "",
            x.get("mes") if x.get("mes") is not None else 13,
            x.get("indicador") or "",
        )
    )

    return jsonify(data_acumulada)



def procesar_tabla_estatica(
    tabla,
    alias,
    columnas,
    indicadores_solicitados,
    es_descarga_masiva,
    unidades,
    anios,
    cur,
    es_anual,
    meses_validos,
    data_acumulada,
):
    columnas_norm = {c.lower().strip(): c for c in columnas}

    solicitados = [
        columnas_norm[i.lower().strip()]
        for i in indicadores_solicitados
        if i.lower().strip() in columnas_norm
    ]

    # Si no es descarga masiva y el indicador solicitado no pertenece a esta tabla estática, salir rápido
    if not es_descarga_masiva and not solicitados:
        return

    columnas_finales = columnas if es_descarga_masiva else solicitados
    columnas_sql = ", ".join([f"{alias}.`{c}`" for c in columnas_finales])

    query = f"""
    SELECT
        {alias}.anio,
        {alias}.clues,
        COALESCE(c.nombre_unidad, CONCAT('Unidad ', {alias}.clues)) AS nombre_unidad,
        COALESCE(c.tipologia, 'TODAS') AS tipologia,
        {columnas_sql}
    FROM {tabla} {alias}
    LEFT JOIN catalogo_unidades c
        ON {alias}.clues = c.clues
    WHERE 1=1
    """

    params = []

    if unidades:
        query += f" AND {alias}.clues IN ({','.join(['%s'] * len(unidades))})"
        params.extend(unidades)

    if anios:
        query += f" AND {alias}.anio IN ({','.join(['%s'] * len(anios))})"
        params.extend(anios)

    cur.execute(query, params)
    rows = cur.fetchall()

    for r in rows:
        meses_generar = [13] if es_anual else meses_validos

        for mes in meses_generar:
            for indicador in columnas_finales:
                data_acumulada.append(
                    {
                        "anio": r["anio"],
                        "mes": 13 if es_anual else mes,
                        "clues": r["clues"],
                        "nombre_unidad": r["nombre_unidad"],
                        "tipologia": r.get("tipologia", "TODAS"),
                        "indicador": indicador.lower(),
                        "valor": float(r.get(indicador, 0) or 0),
                    }
                )



@grafica.route("/api/unidades")
@login_required
def unidades():
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    # Hacemos JOIN con el catálogo para traer el nombre real
    # COALESCE asegura que si no hay nombre en el catálogo, use el de la vista
    cur.execute("""
        SELECT DISTINCT 
            v.clues, 
            COALESCE(c.nombre_unidad, v.nombre_unidad) AS nombre_unidad,
            c.tipologia 
        FROM vw_indicadores_unificados v
        LEFT JOIN catalogo_unidades c ON v.clues = c.clues
        WHERE v.clues IS NOT NULL
        ORDER BY nombre_unidad
    """)
    unidades_raw = cur.fetchall()
    cur.close()

    return jsonify(unidades_raw)

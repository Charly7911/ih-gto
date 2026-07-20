import MySQLdb
from flask import Blueprint, current_app, request, jsonify, render_template
from flask_login import login_required, current_user
from app.controllers.egresos_controller import obtener_indicador
from app import mysql
import calendar
from collections import defaultdict
import sys

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
# FUNCIÓN TOTAL GENERAL
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
    
    # ==========================================
    # IDENTIFICAR UNIDADES Y CONDICIÓN ANUAL
    # ==========================================
    unidades = {
        r["nombre_unidad"]
        for r in data_acumulada
        if r["nombre_unidad"] != "TOTAL GENERAL"
    }
    
    # Detectamos si es formato anual
    es_anual = len(meses_validos) == 12 or any(r["mes"] == 13 for r in data_acumulada)

    if not data_acumulada:
        return []

    # REGLA ANUAL: Si la descarga es ANUAL y solo hay UNA unidad, NO se genera Total General
    if len(unidades) == 1 and es_anual:
        return []

    resultados = []
    
    # ==========================================
    # CASO 1: UNA SOLA UNIDAD - DESCARGA MENSUAL
    # ==========================================
    if len(unidades) == 1 and not es_anual:
        anios_presentes = {r["anio"] for r in data_acumulada}
        
        for anio in anios_presentes:
            registros_anio = [
                r for r in data_acumulada 
                if r["anio"] == anio 
                and r["nombre_unidad"] != "TOTAL GENERAL" 
                and r["mes"] != 13
            ]
            
            if not registros_anio:
                continue
                
            base = {}
            for campo in SUM_FIELDS:
                base[campo] = sum(float(x["valor"]) for x in registros_anio if x["indicador"] == campo)

            for campo in MAX_FIELDS:
                valores = [float(x["valor"]) for x in registros_anio if x["indicador"] == campo]
                base[campo] = sum(valores) if valores else 0  # <--- Suma acumulada de la unidad

            meses_en_registro = {r["mes"] for r in registros_anio}
            dias = sum(calendar.monthrange(anio, m)[1] for m in meses_en_registro)

            kpis = calcular_kpis(base, dias)
            dataset = {**base, **kpis}

            nombre_meses = {1: "Ene", 2: "Feb", 3: "Mar", 4: "Abr", 5: "May", 6: "Jun", 
                            7: "Jul", 8: "Ago", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dic"}
            min_m = min(meses_en_registro)
            max_m = max(meses_en_registro)
            texto_mes = f"{nombre_meses[min_m]} - {nombre_meses[max_m]}" if min_m != max_m else nombre_meses[min_m]

            for indicador, valor in dataset.items():
                indicador = indicador.lower()
                if es_descarga_masiva or indicador in indicadores_solicitados:
                    resultados.append({
                        "anio": anio,
                        "mes": texto_mes,  
                        "clues": "TOTAL",
                        "nombre_unidad": "TOTAL GENERAL",
                        "indicador": indicador,
                        "valor": round(float(valor), 2)
                    })
                    
        return resultados
    
    # ==========================================
    # CASO 2: VARIAS UNIDADES - DESCARGA ANUAL
    # ==========================================
    if len(unidades) > 1 and es_anual:
        anios_presentes = {r["anio"] for r in data_acumulada}

        for anio in anios_presentes:
            registros_anio = [
                r for r in data_acumulada
                if r["anio"] == anio
                and r["nombre_unidad"] != "TOTAL GENERAL"
            ]

            base = {}
            for campo in SUM_FIELDS:
                base[campo] = sum(float(x["valor"]) for x in registros_anio if x["indicador"] == campo)

            for campo in MAX_FIELDS:
                valores = [float(x["valor"]) for x in registros_anio if x["indicador"] == campo]
                base[campo] = sum(valores) if valores else 0 # <--- Suma acumulada anual de todas las unidades

            dias = sum(calendar.monthrange(anio, m)[1] for m in meses_validos)
            kpis = calcular_kpis(base, dias)
            dataset = {**base, **kpis}

            for indicador, valor in dataset.items():
                indicador = indicador.lower()
                if es_descarga_masiva or indicador in indicadores_solicitados:
                    resultados.append({
                        "anio": anio,
                        "mes": 13,
                        "clues": "TOTAL",
                        "nombre_unidad": "TOTAL GENERAL",
                        "indicador": indicador,
                        "valor": round(float(valor), 2)
                    })

        return resultados

    # ==========================================
    # CASO 3: VARIAS UNIDADES - DESCARGA MENSUAL
    # (Comportamiento normal por cada mes/año)
    # ==========================================
    grupos = defaultdict(list)
    for r in data_acumulada:
        if r["nombre_unidad"] != "TOTAL GENERAL":
            grupos[(r["anio"], r["mes"])].append(r)

    for (anio, mes), registros in grupos.items():
        if mes == 13:
            continue

        base = {}
        for campo in SUM_FIELDS:
            base[campo] = sum(float(x["valor"]) for x in registros if x["indicador"] == campo)

        # ¡CORRECCIÓN CLAVE AQUÍ!
        # Se cambió max(valores) por sum(valores) para que los totales de cada mes también sumen
        for campo in MAX_FIELDS:
            valores = [float(x["valor"]) for x in registros if x["indicador"] == campo]
            base[campo] = sum(valores) if valores else 0  # <--- Cambiado de max() a sum()

        dias = calendar.monthrange(anio, mes)[1]
        kpis = calcular_kpis(base, dias)
        dataset = {**base, **kpis}

        for indicador, valor in dataset.items():
            indicador = indicador.lower()
            if es_descarga_masiva or indicador in indicadores_solicitados:
                resultados.append({
                    "anio": anio,
                    "mes": mes,
                    "clues": "TOTAL",
                    "nombre_unidad": "TOTAL GENERAL",
                    "indicador": indicador,
                    "valor": round(float(valor), 2)
                })

    return resultados



@grafica.route("/api/indicadores")
@login_required
def indicadores():

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

    # ==========================================================
    # PARAMETROS
    # ==========================================================

    unidades = (
        request.args.getlist("clues[]")
        or request.args.getlist("unidades[]")
        or request.args.getlist("clues")
    )

    anios_raw = request.args.getlist("anios[]") or request.args.getlist("anios")
    meses_raw = request.args.getlist("meses[]")

    indicadores_solicitados = (
        request.args.getlist("indicadores[]")
        or request.args.getlist("indicadores")
    )

    indicadores_solicitados = [i.strip().lower() for i in indicadores_solicitados]

    # ==========================================================
    # NORMALIZAR
    # ==========================================================

    anios = [int(a) for a in anios_raw if str(a).isdigit()]
    meses = [int(m) for m in meses_raw if str(m).isdigit()]

    quiere_anual = 13 in meses
    es_anual = quiere_anual

    meses_validos = [m for m in meses if m != 13]

    if not meses_validos:
        meses_validos = list(range(1, 13))

    meses_calculo = meses_validos

  
    # ==========================================================
    # FLAGS DE EJECUCIÓN
    # ==========================================================

    es_descarga_masiva = len(indicadores_solicitados) == 0

    quiere_kpis = es_descarga_masiva or any(
        i in kpis_calculados for i in indicadores_solicitados
    )

    quiere_vistas = es_descarga_masiva or any(
        i not in kpis_calculados for i in indicadores_solicitados
    )

    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    data_acumulada = []

    # ==========================================================
    # CONFIGURACIÓN BASE DE GROUP BY
    # ==========================================================

    group_by_cols = [
        "e.anio",
        "e.clues",
        "e.nombre_unidad",
    ]

    if not quiere_anual:
        group_by_cols.append("e.mes")

    # si NO es anual, agregamos mes
   

    group_by = ",\n".join(group_by_cols)

    select_mes = "e.mes," if not quiere_anual else "13 AS mes,"

    # ==========================================================
    # KPIS
    # ==========================================================

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

        # ======================================================
        # QUERY PRINCIPAL
        # ======================================================

        if es_anual:
            agg_camas = "AVG"
        else:
            agg_camas = "MAX"
        
        query_e = f"""
                SELECT 
                    e.anio,
                    {select_mes}
                    e.clues,
                    e.nombre_unidad,

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
                    MAX(IFNULL(cnc.hab_urgencias, 0)) AS hab_urgencias,
                    MAX(IFNULL(cnc.hab_observacion, 0)) AS hab_observacion,
                    MAX(IFNULL(cnc.hab_cuid_int, 0)) AS hab_cuid_int,
                    MAX(IFNULL(cnc.hab_cirug_amb, 0)) AS hab_cirug_amb,
                    MAX(IFNULL(cnc.hab_quemados, 0)) AS hab_quemados,
                    MAX(IFNULL(cnc.hab_lab_parto, 0)) AS hab_lab_parto,
                    MAX(IFNULL(cnc.hab_recup_pp, 0)) AS hab_recup_pp,
                    MAX(IFNULL(cnc.hab_recup_pq, 0)) AS hab_recup_pq,
                    MAX(IFNULL(cnc.hab_uci_adulto, 0)) AS hab_uci_adulto,
                    MAX(IFNULL(cnc.hab_uci_ped, 0)) AS hab_uci_ped,
                    MAX(IFNULL(cnc.hab_otras_areas, 0)) AS hab_otras_areas,
                    MAX(IFNULL(cnc.total_no_censables, 0)) AS total_no_censables

                FROM egresos_agregado e

                -- JOIN ABORTOS (GRUPAL POR MES)
                LEFT JOIN (
                    SELECT anio, mes, clues,
                        SUM(lui) AS abortos_lui, SUM(ameu) AS abortos_ameu,
                        SUM(medicamento) AS abortos_medicado, SUM(no_especificado) AS abortos_no_especificado,
                        SUM(total) AS abortos_total
                    FROM abortos GROUP BY anio, mes, clues
                ) ab ON e.clues = ab.clues AND e.anio = ab.anio AND e.mes = ab.mes

                -- JOIN SIS (GRUPAL POR MES)
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

                -- JOIN URGENCIAS (GRUPAL POR MES)
                LEFT JOIN (
                    SELECT anio, mes_estadistico, clues,
                        SUM(total) AS total_u, SUM(calificada) AS calificada,
                        SUM(no_calificada) AS no_calificada, SUM(medica) AS medica,
                        SUM(accidentes) AS accidentes, SUM(pediatrica) AS pediatrica,
                        SUM(ginecobstetricia) AS ginecobstetricia
                    FROM urgencias_agregado GROUP BY anio, mes_estadistico, clues
                ) urg ON e.clues = urg.clues AND e.anio = urg.anio AND e.mes = urg.mes_estadistico

                -- JOIN PROCEDIMIENTOS (GRUPAL POR MES)
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
                        SUM(
                            IFNULL(med_int_proced_dentro,0) +
                            IFNULL(med_int_proced_fuera,0)
                        ) AS total_proced_med_int,

                        SUM(
                            IFNULL(cirugia_proced_dentro,0) +
                            IFNULL(cirugia_proced_fuera,0)
                        ) AS total_proced_cirugia,

                        SUM(
                            IFNULL(gineco_proced_dentro,0) +
                            IFNULL(gineco_proced_fuera,0)
                        ) AS total_proced_gineco,

                        SUM(
                            IFNULL(pediatra_proced_dentro,0) +
                            IFNULL(pediatra_proced_fuera,0)
                        ) AS total_proced_pediatria,

                        SUM(
                            IFNULL(otros_proced_dentro,0) +
                            IFNULL(otros_proced_fuera,0)
                        ) AS total_proced_otros,

                        -- TOTAL GENERAL
                        SUM(
                            IFNULL(total_proced_dentro,0) +
                            IFNULL(total_proced_fuera,0)
                        ) AS total_proced
                    FROM procedimiento_agregado GROUP BY anio, mes, clues
                ) p ON e.clues = p.clues AND e.anio = p.anio AND e.mes = p.mes

                -- JOIN SINERHIAS (ANUAL)
               LEFT JOIN (
                    SELECT
                        anio,
                        mes,
                        clues,
                        total AS camas_total,
                        quirofanos,
                        med_int AS camas_med_int,
                        cirugia AS camas_cirugia,
                        gineco AS camas_gineco,
                        pediatria AS camas_pediatria,
                        otros AS camas_otros
                    FROM sinerhias
                ) sin
                ON e.clues = sin.clues
                AND e.anio = sin.anio
                AND e.mes = sin.mes

                -- JOIN CAMAS NO CENSABLES (ANUAL)
                LEFT JOIN (
                    SELECT anio, clues,
                        MAX(hab_urgencias) AS hab_urgencias, MAX(hab_observacion) AS hab_observacion,
                        MAX(hab_cuid_int) AS hab_cuid_int, MAX(hab_cirug_amb) AS hab_cirug_amb,
                        MAX(hab_quemados) AS hab_quemados, MAX(hab_lab_parto) AS hab_lab_parto,
                        MAX(hab_recup_pp) AS hab_recup_pp, MAX(hab_recup_pq) AS hab_recup_pq,
                        MAX(hab_uci_adulto) AS hab_uci_adulto, MAX(hab_uci_ped) AS hab_uci_ped,
                        MAX(hab_otras_areas) AS hab_otras_areas,
                        (IFNULL(MAX(hab_urgencias),0)+IFNULL(MAX(hab_observacion),0)+IFNULL(MAX(hab_cuid_int),0)+IFNULL(MAX(hab_cirug_amb),0)+IFNULL(MAX(hab_quemados),0)+IFNULL(MAX(hab_lab_parto),0)+IFNULL(MAX(hab_recup_pp),0)+IFNULL(MAX(hab_recup_pq),0)+IFNULL(MAX(hab_uci_adulto),0)+IFNULL(MAX(hab_uci_ped),0)+IFNULL(MAX(hab_otras_areas),0)) AS total_no_censables
                    FROM camas_no_censables GROUP BY anio, clues
                ) cnc ON e.clues = cnc.clues AND e.anio = cnc.anio

                {where_e}

                GROUP BY {group_by}

                """

        cur.execute(query_e, params_e)
        rows_e = cur.fetchall()    

       
        # ==========================================================
        # FUNCIONES
        # ==========================================================
        def f(value):
            return float(value or 0)
        
        
        def calcular_ocupacion(dias_estancia, dias_cama):
            dias_estancia = float(dias_estancia or 0)
            dias_cama = float(dias_cama or 0)
            return (dias_estancia / dias_cama) * 100 if dias_cama else 0
        

        

        def calcular_kpis(data, dias):
           
            egresos = f(data["total_egresos"])

           
            camas = f(data["camas_total"])
            camas_med_int = f(data["camas_med_int"])
            camas_cirugia = f(data["camas_cirugia"])
            camas_pediatria = f(data["camas_pediatria"])
            camas_gineco = f(data["camas_gineco"])
            camas_otros = f(data["camas_otros"])

            dias_est_med = f(data["dias_est_med"])
            dias_est_cir = f(data["dias_est_cir"])
            dias_est_ped = f(data["dias_est_ped"])
            dias_est_gin = f(data["dias_est_gin"])
            dias_est_otr = f(data["dias_est_otros"])

            egresos_med = f(data["egre_med_interna"])
            egresos_cir = f(data["egre_cirugia"])
            egresos_ped = f(data["egre_pediatria"])
            egresos_gin = f(data["egre_gineco"])
            egresos_otr = f(data["egre_otros"])
            quirofanos = f(data["quirofanos"])

            nacimientos = f(data["total_nacimientos"])
            abortos = f(data["abortos"])

            eventos = nacimientos + abortos
            egresos = f(data["total_egresos"])
            adolescente_apeo = f(data["adolescente_apeo"])
            eventos_obstetricos_adolescentes = f(data["eventos_obstetricos_adolescentes"])

            camas = f(data["camas_total"])
            camas_pediatria = f(data["camas_pediatria"])
            dias_est_ped = f(data["dias_est_ped"])

          

           
            return {
                # ======================================================
                # KPI
                # ======================================================
                "consultas_por_dia": f(data["consultas"]) / dias if dias else 0,
                "especialidad_por_dia": f(data["especialidad"]) / dias if dias else 0,
                "urgencias_por_dia": f(data["urgencias"]) / dias if dias else 0,
                "porcentaje_calificada": (
                    (f(data["calificada"]) / f(data["urgencias"]) * 100)
                    if f(data["urgencias"])
                    else 0
                ),
                "nacimientos_por_dia": nacimientos / dias if dias else 0,
                "porcentaje_cesareas": (
                    (f(data["nac_cesarea"]) / nacimientos * 100) if nacimientos else 0
                ),
                "prom_inter_diarias_qx": (
                    round(f(data["total_proced_dentro"]) / (quirofanos * dias), 2)
                    if quirofanos and dias
                    else 0
                ),
                "porcentaje_apeo": (f(data["apeo"]) / eventos * 100) if eventos else 0,

                "porcentaje_adolescente_apeo": (
                    (adolescente_apeo * 100) / eventos_obstetricos_adolescentes
                    if eventos_obstetricos_adolescentes
                    else 0
                ),

                "porcentaje_ocupacion": calcular_ocupacion(f(data["dias_p"]), f(data["dias_cama_total"])),

                "porcentaje_ocupacion_med_interna": calcular_ocupacion(dias_est_med, f(data["dias_cama_med"])),

                "porcentaje_ocupacion_cirugia": calcular_ocupacion(dias_est_cir, f(data["dias_cama_cir"])),

                "porcentaje_ocupacion_pediatria": calcular_ocupacion(dias_est_ped, f(data["dias_cama_ped"])),

                "porcentaje_ocupacion_gineco": calcular_ocupacion(dias_est_gin, f(data["dias_cama_gin"])),

                "porcentaje_ocupacion_otros": calcular_ocupacion(dias_est_otr, f(data["dias_cama_otros"])),


                "prom_dias_estancia": (
                    (f(data["dias_estancia"]) / egresos) if egresos else 0
                ),
                # ============================
                # PROMEDIO DE ESTANCIA POR SERVICIO
                # ============================
                "prom_estancia_med_interna":
                    (dias_est_med / egresos_med) if egresos_med else 0,

                "prom_estancia_cirugia":
                    (dias_est_cir / egresos_cir) if egresos_cir else 0,

                "prom_estancia_pediatria":
                    (dias_est_ped / egresos_ped) if egresos_ped else 0,

                "prom_estancia_gineco":
                    (dias_est_gin / egresos_gin) if egresos_gin else 0,

                "prom_estancia_otros":
                    (dias_est_otr / egresos_otr) if egresos_otr else 0,



                "indice_rotacion": (egresos / camas) if camas else 0,
                "interv_sustitucion": (
                    (((camas * dias) - f(data["dias_p"])) / egresos) if egresos else 0
                ),
                
                "mortalidad_cruda": (
                    (f(data["egre_defunciones"]) * 1000 / egresos) if egresos else 0
                ),
                "mortalidad_ajustada": (
                    (
                        f(data["egre_defunciones_48h"])
                        * 1000
                        / f(data["total_egresos_48h"])
                    )
                    if f(data["total_egresos_48h"])
                    else 0
                ),
            }
        
       
        # ==========================================================
        # RECORRER ROWS
        # ==========================================================      

        for r in rows_e:

            anio = int(r["anio"])
            mes = int(r["mes"]) if r.get("mes") else 13
            unidad = r["nombre_unidad"]
            

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
                        "nombre_unidad": unidad,
                        "indicador": indicador_norm,
                        "valor": round(valor, 2),
                    })
    # ==========================================================
    # PARTE 2: INDICADORES DE VISTA
    # ==========================================================

    indicadores_ya_calculados = {field.lower() for field in SUM_FIELDS + MAX_FIELDS}

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
            v.valor
        FROM vw_indicadores_unificados v
        LEFT JOIN catalogo_unidades c
            ON v.clues = c.clues
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
                        "indicador": indicador,
                        "valor": round(valor, 2),
                    }
                )

        # ======================================================
        # GENERAR MES 13
        # ======================================================

        if es_anual:

            for (anio, clues, unidad, indicador), valor in vista_cache.items():

                if indicador in indicadores_ya_calculados:
                    continue

                data_acumulada.append(
                    {
                        "anio": anio,
                        "mes": 13,
                        "clues": clues,
                        "nombre_unidad": unidad,
                        "indicador": indicador,
                        "valor": round(valor, 2),
                    }
                )

    cols_no_censables = [
        "hab_urgencias",
        "inh_urgencias",
        "tot_urgencias",
        "hab_observacion",
        "inh_observacion",
        "tot_observacion",
        "hab_cuid_int",
        "inh_cuid_int",
        "tot_cuid_int",
        "hab_cirug_amb",
        "inh_cirug_amb",
        "tot_cirug_amb",
        "hab_quemados",
        "inh_quemados",
        "tot_quemados",
        "hab_lab_parto",
        "inh_lab_parto",
        "tot_lab_parto",
        "hab_recup_pp",
        "inh_recup_pp",
        "tot_recup_pp",
        "hab_recup_pq",
        "inh_recup_pq",
        "tot_recup_pq",
        "hab_uci_adulto",
        "inh_uci_adulto",
        "tot_uci_adulto",
        "hab_uci_ped",
        "inh_uci_ped",
        "tot_uci_ped",
        "hab_otras_areas",
        "inh_otras_areas",
        "tot_otras_areas",
    ]

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

    # ==========================================================
    # PARTE 3 Y 4
    # ==========================================================

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
    # TOTAL GENERAL
    # ==========================================================

    data_acumulada.extend(
        generar_total_general(
            data_acumulada=data_acumulada,
            meses_validos=meses_validos,
            SUM_FIELDS=SUM_FIELDS,
            MAX_FIELDS=MAX_FIELDS,
            indicadores_max=indicadores_max,
            calcular_kpis=calcular_kpis,
            es_descarga_masiva=es_descarga_masiva,
            indicadores_solicitados=indicadores_solicitados,
        )
    )



    # ==========================================================
    # CIERRE
    # ==========================================================

    cur.close()

    data_acumulada.sort(
        key=lambda x: (
            x["anio"],
            x["nombre_unidad"],
            x["mes"] if x["mes"] is not None else 13,
            x["indicador"],
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

    columnas_finales = columnas if es_descarga_masiva else solicitados

    columnas_sql = ", ".join([f"{alias}.`{c}`" for c in columnas_finales])

    if not es_descarga_masiva and not solicitados:
        return

    query = f"""
    SELECT
        {alias}.anio,
        {alias}.clues,
        c.nombre_unidad,
        {columnas_sql}
    FROM {tabla} {alias}
    LEFT JOIN catalogo_unidades c
        ON {alias}.clues = c.clues
    WHERE 1=1
    """

    params = []

    if unidades:
        query += " AND {0}.clues IN ({1})".format(
            alias, ",".join(["%s"] * len(unidades))
        )
        params.extend(unidades)

    if anios:
        query += " AND {0}.anio IN ({1})".format(alias, ",".join(["%s"] * len(anios)))
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
                        "nombre_unidad": (r["nombre_unidad"] or f"Unidad {r['clues']}"),
                        "indicador": indicador,
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

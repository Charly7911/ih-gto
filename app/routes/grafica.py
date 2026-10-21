import math

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
# FUNCIÓN TOTAL GENERAL (SIN DUPLICACIÓN DE DATOS)
# ==========================================================
def generar_total_general(
    data_acumulada,
    meses_validos,
    SUM_FIELDS,
    MAX_FIELDS,
    indicadores_max=None, # 👈 VALOR POR DEFECTO DEFENSIVO
    calcular_kpis=None,
    es_descarga_masiva=False,
    indicadores_solicitados=None,
):
    if indicadores_max is None:
        indicadores_max = {}

    if not callable(calcular_kpis):
        # Evita lanzar UnboundLocalError / TypeError
        def calcular_kpis(data, dias):
            return {}

    RECURSOS_FISICOS = [
        "camas_total", "quirofanos", "camas_med_int", "camas_cirugia",
        "camas_gineco", "camas_pediatria", "camas_otros", "hab_urgencias",
        "hab_observacion", "hab_quemados", "hab_lab_parto", "hab_recup_pp",
        "hab_cirug_amb", "hab_recup_pq", "hab_cuid_int", "hab_uci_adulto",
        "hab_uci_ped", "hab_otras_areas", "total_no_censables",
    ]

    # 🔑 FIX 1: INCLUIR EQUIPO MÉDICO EN SUM_FIELDS O MÁXIMOS
    indicadores_equipo_medico = {
        "arco_c_analogo", "arco_c_digital", "bascula_estadimetro", "bascula_bebe",
        "camilla_radiotransp", "cardiotocografo", "carro_rojo_reanim", "cuna_calor_rad",
        "cuna_calor_rad_foto", "defibrilador_monit", "ecocardiografo", "electrocardiografo",
        "estuche_diag", "incubadora_fototer", "incubadora_trasl", "incubadora_cuidados",
        "lampara_quirurgica_doble", "lampara_quir_port", "lampara_quir_senc", "mesa_quir_obs",
        "mesa_exploracion", "mesa_quir_gral", "microscopio_rutina", "monitor_radiacion",
        "monitor_signos_vit_avanz", "monitor_signos_neo", "monitor_signos_bas", "monitor_traslado",
        "monitor_signos_int", "monitor_signos_vit_neona", "monitor_anestesia", "negatoscopio",
        "refrige_lab", "sierra_yesos", "ultrasonido_diag", "unidad_anestesia_bas",
        "ultrasonido_terap", "unidad_dental", "unidad_rx_analogo", "unidad_rx_dental",
        "unidad_rx_digital", "unidad_rx_port_ana", "unidad_rx_port_dig", "fluoroscopio_dig",
        "fluoroscopio_dig_analog", "mastografo_digital", "mastografo_estereo",
        "mastografo_estereo_tomosin", "microscopio_cirugia", "resonancia_mag",
        "tomografo_128", "tomografo_16", "tomografo_32", "tomografo_64",
    }

    # Asegurar que los campos de equipo médico se puedan sumar/consolidar
    SUM_FIELDS = set(SUM_FIELDS) | indicadores_equipo_medico if SUM_FIELDS else indicadores_equipo_medico

    if not data_acumulada:
        return []

    indicadores_solic_set = (
        {ind.lower() for ind in indicadores_solicitados}
        if isinstance(indicadores_solicitados, (list, set, tuple)) and indicadores_solicitados
        else set()
    )

    recursos_set = {r.lower() for r in RECURSOS_FISICOS}
    sum_fields_set = {s.lower() for s in SUM_FIELDS}

    # 🔑 1. DEPURACIÓN DE REGISTROS: Extraer sólo unidades individuales para evitar doble suma
    registros_individuales = [
        r for r in data_acumulada 
        if r.get("clues") != "TOTAL" and r.get("nombre_unidad") not in ["TOTAL GENERAL", "TOTAL GRUPO"]
        and not str(r.get("clues", "")).startswith("GRUPO_")
    ]

    data_limpia = registros_individuales if registros_individuales else data_acumulada

    unidades = {
        r.get("nombre_unidad")
        for r in data_limpia
        if r.get("clues") != "TOTAL"
    }

    es_anual = any(r.get("mes") == 13 for r in data_limpia)

    if len(unidades) == 1 and es_anual:
        return []

    resultados = []

    # ==========================================
    # AUXILIAR: CONSTRUIR BASE (ROBUSTA Y DEDUPLICADA)
    # ==========================================
    def construir_base(registros):
        base = defaultdict(float)
        recursos_map = defaultdict(lambda: defaultdict(float))

        # 🧪 PRINT C: REVISAR REGISTROS QUE LLEGAN A CONSTRUIR BASE POR MES
        if registros:
            mes_actual = registros[0].get("mes")
            unidades_in = set(r.get("clues") for r in registros)
            egresos_in = [r for r in registros if str(r.get("indicador")).lower() == "total_egresos"]
            suma_egr = sum(float(r.get("valor") or 0) for r in egresos_in)
          

        # 🔑 Deduplicar registros por (anio, mes, clues, indicador)
        vistos = set()
        registros_unicos = []
        for x in registros:
            clave = (x.get("anio"), x.get("mes"), x.get("clues"), str(x.get("indicador", "")).lower())
            if clave not in vistos:
                vistos.add(clave)
                registros_unicos.append(x)

        # 1. Recursos Físicos (Máximo por unidad entre meses, luego suma)
        recursos_map = defaultdict(lambda: defaultdict(float))
        for x in registros_unicos:
            indicador = str(x.get("indicador", "")).lower()
            unidad = x.get("nombre_unidad", "UNIDAD")
            
            # Buscar en el campo 'indicador' o en las llaves del diccionario
            if indicador in recursos_set:
                val = float(x.get("valor") or 0)
                if val > recursos_map[indicador][unidad]:
                    recursos_map[indicador][unidad] = val

            for col_nombre, col_valor in x.items():
                col_lower = str(col_nombre).lower().strip()
                if col_lower in recursos_set:
                    try:
                        val_num = float(col_valor or 0)
                        if val_num > recursos_map[col_lower][unidad]:
                            recursos_map[col_lower][unidad] = val_num
                    except (ValueError, TypeError):
                        continue

        for campo in RECURSOS_FISICOS:
            campo_lower = campo.lower()
            base[campo_lower] = sum(recursos_map[campo_lower].values())

        # 2. Campos Sumables (Extrae tanto de la propiedad 'indicador' como de las llaves físicas)
        for campo in SUM_FIELDS:
            campo_lower = campo.lower()
            suma_campo = 0.0

            for x in registros_unicos:
                # Opción A: Si viene como fila vertical (indicador == 'tomografo_64')
                if str(x.get("indicador", "")).lower() == campo_lower:
                    suma_campo += float(x.get("valor") or 0)
                # Opción B: Si viene como columna horizontal/atributo ('tomografo_64': 2)
                elif campo_lower in x:
                    try:
                        suma_campo += float(x.get(campo_lower) or 0)
                    except (ValueError, TypeError):
                        pass

            base[campo_lower] = suma_campo

        # 3. Campos Máximos
        for campo in MAX_FIELDS:
            campo_lower = campo.lower()
            if campo_lower not in recursos_set and campo_lower not in sum_fields_set:
                valores = []
                for x in registros_unicos:
                    if str(x.get("indicador", "")).lower() == campo_lower:
                        valores.append(float(x.get("valor") or 0))
                    elif campo_lower in x:
                        try:
                            valores.append(float(x.get(campo_lower) or 0))
                        except (ValueError, TypeError):
                            pass
                base[campo_lower] = max(valores) if valores else 0.0

        return base

    # ==========================================
    # CASO 1: UNA SOLA UNIDAD - MENSUAL
    # ==========================================
    if len(unidades) == 1 and not es_anual:
        anios_presentes = {r["anio"] for r in data_limpia if "anio" in r}

        for anio in anios_presentes:
            registros_anio = [
                r for r in data_limpia
                if r.get("anio") == anio and r.get("mes") != 13
            ]

            if not registros_anio:
                continue

            base = construir_base(registros_anio)
            meses_en_registro = {int(r["mes"]) for r in registros_anio if r.get("mes") is not None}

            dias = sum(calendar.monthrange(anio, m)[1] for m in meses_en_registro) if meses_en_registro else 30
            
            dataset = dict(base)
            if callable(calcular_kpis):
                kpis = calcular_kpis(base, dias)
                dataset.update(kpis)

            mes_rep = max(meses_en_registro) if meses_en_registro else 12

            for indicador, valor in dataset.items():
                ind_lower = str(indicador).lower()
                if es_descarga_masiva or ind_lower in indicadores_solic_set:
                    resultados.append({
                        "anio": anio,
                        "mes": mes_rep,
                        "clues": "TOTAL",
                        "nombre_unidad": "TOTAL GENERAL",
                        "tipologia": "TODAS",
                        "indicador": ind_lower,
                        "valor": round(float(valor or 0), 2)
                    })

        return resultados

    # ==========================================
    # CASO 2: VARIAS UNIDADES - ANUAL (MES 13)
    # ==========================================
    if len(unidades) > 1 and es_anual:
        anios_presentes = {r["anio"] for r in data_limpia if "anio" in r}

        for anio in anios_presentes:
            registros_anio = [r for r in data_limpia if r.get("anio") == anio]

            base = construir_base(registros_anio)

            if meses_validos:
                dias = sum(calendar.monthrange(anio, m)[1] for m in meses_validos)
            else:
                dias = 365

            dataset = dict(base)
            if callable(calcular_kpis):
                kpis = calcular_kpis(base, dias)
                dataset.update(kpis)

            for indicador, valor in dataset.items():
                ind_lower = str(indicador).lower()
                if es_descarga_masiva or ind_lower in indicadores_solic_set:
                    resultados.append({
                        "anio": anio,
                        "mes": 13,
                        "clues": "TOTAL",
                        "nombre_unidad": "TOTAL GRUPO",
                        "tipologia": "TODAS",
                        "indicador": ind_lower,
                        "valor": round(float(valor or 0), 2)
                    })

        return resultados

    # ==========================================
    # CASO 3: VARIAS UNIDADES - MENSUAL (DESGLOSE MES A MES)
    # ==========================================
    grupos = defaultdict(list)

    for r in data_limpia:
        if r.get("mes") is not None and r.get("mes") != 13 and r.get("anio"):
            grupos[(r["anio"], int(r["mes"]))].append(r)

    for (anio, mes), registros in grupos.items():
        base = construir_base(registros)
        dias = calendar.monthrange(anio, mes)[1] if (anio and anio > 0) else 30

        dataset = dict(base)
        if callable(calcular_kpis):
            kpis = calcular_kpis(base, dias)
            dataset.update(kpis)

        for indicador, valor in dataset.items():
            ind_lower = str(indicador).lower()
            if es_descarga_masiva or ind_lower in indicadores_solic_set:
                resultados.append({
                    "anio": anio,
                    "mes": mes,
                    "clues": "TOTAL",
                    "nombre_unidad": "TOTAL GRUPO",
                    "tipologia": "TODAS",
                    "indicador": ind_lower,
                    "valor": round(float(valor or 0), 2)
                })

    return resultados




@grafica.route("/api/indicadores")
@login_required
def indicadores():

    cols_equipo_medico = []
    indicadores_max = {}
    calcular_kpis = None
    

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
        "prom_estancia_med_int",
        "prom_estancia_med_interna",
        "prom_dias_estancia_med_interna",
        
        "prom_estancia_cir",
        "prom_estancia_cirugia",
        "prom_dias_estancia_cirugia",
        
        "prom_estancia_ped",
        "prom_estancia_pediatria",
        "prom_dias_estancia_pediatria",
        
        "prom_estancia_gin",
        "prom_estancia_gineco",
        "prom_dias_estancia_gineco",
        
        "prom_estancia_otr",
        "prom_estancia_otros",
        "prom_dias_estancia_otros",
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

    # 🔑 RECOLECCIÓN DE CLUES DE GRUPOS (HG, HC, HE, TODAS):
    # Si viene vacía 'unidades', extraemos todas las CLUES enviadas en los arreglos 'grupo_X_clues[]'
    for key in request.args.keys():
        if key.startswith("grupo_") and key.endswith("_clues[]"):
            unidades.extend(request.args.getlist(key))

    # Deduplicar
    unidades = list(set([u for u in unidades if u]))

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
        or i in DEPENDENCIAS_KPIS # 👈 Si está en las dependencias, ¡también quiere KPIs!
        or i.startswith("prom_estancia_")
        or i.startswith("prom_dias_estancia")
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

    # 🔑 Para que Python pueda agrupar por cada subgrupo, la consulta SQL siempre 
    # debe traer el desglose por CLUES. De esa forma 'generar_total_general'
    # suma los absolutos y calcula la mortalidad/ocupación exacta por grupo.
    group_by_cols = ["b.anio", "b.clues", "COALESCE(c.nombre_unidad, b.clues)", "COALESCE(c.tipologia, 'TODAS')"]
    select_unidad = "b.clues, COALESCE(c.nombre_unidad, b.clues) AS nombre_unidad, COALESCE(c.tipologia, 'TODAS') AS tipologia,"

    if not quiere_anual:
        group_by_cols.append("b.mes")

    group_by = ",\n".join(group_by_cols)
    select_mes = "b.mes," if not quiere_anual else "13 AS mes,"

    agg_camas = "AVG" if quiere_anual else "MAX"

    # ==========================================================
    # KPIS
    # ==========================================================

    rows_e = []

    if quiere_kpis:

        where_e = "WHERE 1=1"
        params_e = []

        if unidades:
            where_e += " AND b.clues IN ({})".format(",".join(["%s"] * len(unidades)))
            params_e.extend(unidades)

        if anios:
            where_e += " AND b.anio IN ({})".format(",".join(["%s"] * len(anios)))
            params_e.extend(anios)

        if meses_calculo:
            where_e += " AND b.mes IN ({})".format(",".join(["%s"] * len(meses_calculo)))
            params_e.extend(meses_calculo)

        if tipologia != "TODAS" and not unidades:
            where_e += " AND c.tipologia = %s"
            params_e.append(tipologia)

        # ======================================================
        # QUERY PRINCIPAL
        # ======================================================

        query_e = f"""
        SELECT 
            b.anio,
            {select_mes}
            {select_unidad}

            -- EGRESOS Y NACIMIENTOS (TABLA PRINCIPAL)
            SUM(IFNULL(e.total_egresos, 0)) AS total_egresos,        
            SUM(IFNULL(e.defunciones, 0)) AS egre_defunciones,
            SUM(IFNULL(e.defunciones_48h, 0)) AS egre_defunciones_48h,
            SUM(IFNULL(e.dias_estancia_sum, 0)) AS dias_estancia,
            SUM(IFNULL(e.dias_estancia_med_interna, 0)) AS dias_est_med,
            SUM(IFNULL(e.dias_estancia_cirugia, 0)) AS dias_est_cir,
            SUM(IFNULL(e.dias_estancia_pediatria, 0)) AS dias_est_ped,
            SUM(IFNULL(e.dias_estancia_ginecobstetricia, 0)) AS dias_est_gin,
            SUM(IFNULL(e.dias_estancia_otros, 0)) AS dias_est_otros,
            SUM(IFNULL(e.nacimientos, 0)) AS total_nacimientos,
            SUM(IFNULL(e.nac_distocico, 0)) AS nac_distocico,
            SUM(IFNULL(e.nac_eutocico, 0)) AS nac_eutocico,
            SUM(IFNULL(e.cesareas, 0)) AS nac_cesarea,
            SUM(IFNULL(e.apeo, 0)) AS apeo,
            SUM(IFNULL(e.abortos, 0)) AS abortos,
            SUM(IFNULL(e.abortos, 0) + IFNULL(e.nacimientos, 0)) AS eventos_obstetricos,
            SUM(IFNULL(e.apeo, 0)) AS total_apeo,
            
            SUM(IFNULL(e.med_interna, 0)) AS egre_med_interna,
            SUM(IFNULL(e.cirugia, 0)) AS egre_cirugia,
            SUM(IFNULL(e.pediatria, 0)) AS egre_pediatria,
            SUM(IFNULL(e.ginecobstetricia, 0)) AS egre_gineco,
            SUM(IFNULL(e.otros, 0)) AS egre_otros,

            -- EGRESOS >48H POR SERVICIO
            SUM(IFNULL(e.egresos_med_interna_48h, 0)) AS egre_med_int_48h,
            SUM(IFNULL(e.egresos_cirugia_48h, 0)) AS egre_cirugia_48h,
            SUM(IFNULL(e.egresos_pediatria_48h, 0)) AS egre_pediatria_48h,
            SUM(IFNULL(e.egresos_ginecobstetricia_48h, 0)) AS egre_gineco_48h,
            SUM(IFNULL(e.egresos_otros_48h, 0)) AS egre_otros_48h,
            SUM(IFNULL(e.egresos_48h, 0)) AS total_egresos_48h,

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
            SUM(IFNULL(e.adolescente_apeo, 0)) AS adolescente_apeo,
            SUM(IFNULL(e.eventos_obstetricos_adolescentes, 0)) AS eventos_obstetricos_adolescentes,

            -- RECURSOS FISICOS (KPIs Y SINERHIAS)
            SUM(IFNULL(p.total_proced_dentro, 0)) AS cirugias,
            SUM(IFNULL(sin.camas_total, 0)) AS sinerhias,
            {agg_camas}(IFNULL(sin.camas_total, 0)) AS camas_total,
            {agg_camas}(IFNULL(sin.quirofanos, 0)) AS quirofanos,
            {agg_camas}(IFNULL(sin.camas_med_int, 0)) AS camas_med_int,
            {agg_camas}(IFNULL(sin.camas_cirugia, 0)) AS camas_cirugia,
            {agg_camas}(IFNULL(sin.camas_gineco, 0)) AS camas_gineco,
            {agg_camas}(IFNULL(sin.camas_pediatria, 0)) AS camas_pediatria,
            {agg_camas}(IFNULL(sin.camas_otros, 0)) AS camas_otros,

            -- DÍAS CAMA
            SUM(IFNULL(sin.camas_total, 0) * 30) AS dias_cama_total,
            SUM(IFNULL(sin.camas_med_int, 0) * 30) AS dias_cama_med,
            SUM(IFNULL(sin.camas_cirugia, 0) * 30) AS dias_cama_cir,
            SUM(IFNULL(sin.camas_gineco, 0) * 30) AS dias_cama_gin,
            SUM(IFNULL(sin.camas_pediatria, 0) * 30) AS dias_cama_ped,
            SUM(IFNULL(sin.camas_otros, 0) * 30) AS dias_cama_otros,

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

        FROM (
            SELECT DISTINCT anio, mes, clues FROM egresos_agregado
            UNION
            SELECT DISTINCT anio, mes, clues FROM sinerhias
            UNION
            SELECT DISTINCT anio, mes_estadistico AS mes, clues FROM urgencias_agregado
            UNION
            SELECT DISTINCT anio, mes, clues FROM sis_registros_agregados
            UNION
            SELECT DISTINCT anio, mes, clues FROM procedimiento_agregado
            UNION
            SELECT DISTINCT anio, mes, clues FROM abortos
            UNION
            SELECT DISTINCT anio, mes, clues FROM camas_no_censables
        ) b

        LEFT JOIN catalogo_unidades c ON b.clues = c.clues
        LEFT JOIN egresos_agregado e ON b.clues = e.clues AND b.anio = e.anio AND b.mes = e.mes

        LEFT JOIN (
            SELECT anio, mes, clues,
                SUM(lui) AS abortos_lui, SUM(ameu) AS abortos_ameu,
                SUM(medicamento) AS abortos_medicado, SUM(no_especificado) AS abortos_no_especificado,
                SUM(total) AS abortos_total
            FROM abortos GROUP BY anio, mes, clues
        ) ab ON b.clues = ab.clues AND b.anio = ab.anio AND b.mes = ab.mes

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
        ) sis ON b.clues = sis.clues AND b.anio = sis.anio AND b.mes = sis.mes

        LEFT JOIN (
            SELECT anio, mes_estadistico, clues,
                SUM(total) AS total_u, SUM(calificada) AS calificada,
                SUM(no_calificada) AS no_calificada, SUM(medica) AS medica,
                SUM(accidentes) AS accidentes, SUM(pediatrica) AS pediatrica,
                SUM(ginecobstetricia) AS ginecobstetricia
            FROM urgencias_agregado GROUP BY anio, mes_estadistico, clues
        ) urg ON b.clues = urg.clues AND b.anio = urg.anio AND b.mes = urg.mes_estadistico

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
        ) p ON b.clues = p.clues AND b.anio = p.anio AND b.mes = p.mes

        LEFT JOIN (
            SELECT anio, mes, clues,
                SUM(IFNULL(total, 0)) AS camas_total,
                SUM(IFNULL(quirofanos, 0)) AS quirofanos,
                SUM(IFNULL(med_int, 0)) AS camas_med_int,
                SUM(IFNULL(cirugia, 0)) AS camas_cirugia,
                SUM(IFNULL(gineco, 0)) AS camas_gineco,
                SUM(IFNULL(pediatria, 0)) AS camas_pediatria,
                SUM(IFNULL(otros, 0)) AS camas_otros
            FROM sinerhias GROUP BY anio, mes, clues
        ) sin ON b.clues = sin.clues AND b.anio = sin.anio AND b.mes = sin.mes

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
        ) cnc ON b.clues = cnc.clues AND b.anio = cnc.anio AND b.mes = cnc.mes

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
        ) em ON b.clues = em.clues AND b.anio = em.anio AND b.mes = em.mes

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
        def parse_float(val):
            """Sustituye a f(val): Convierte a float previniendo None, NaN y tipos inválidos"""
            if val is None:
                return 0.0
            try:
                f_val = float(val)
                return 0.0 if math.isnan(f_val) else f_val
            except (ValueError, TypeError):
                return 0.0

        def calcular_ocupacion(dias_paciente, dias_cama):
            dp = parse_float(dias_paciente)
            dc = parse_float(dias_cama)
            return round((dp / dc) * 100.0, 2) if dc > 0 else 0.0

        def calcular_kpis(data, dias):
            # Días del periodo (default 30)
            dias_val = parse_float(dias) if dias and float(dias) > 0 else 30.0

            # Variables base general
            egresos = parse_float(data.get("total_egresos"))
            camas = parse_float(data.get("camas_total"))
            quirofanos = parse_float(data.get("quirofanos"))
            
            nacimientos = parse_float(data.get("total_nacimientos") or data.get("nacimientos"))
            abortos = parse_float(data.get("abortos"))
            eventos = parse_float(data.get("eventos_obstetricos")) or (nacimientos + abortos)

            adolescente_apeo = parse_float(data.get("adolescente_apeo"))
            eventos_obstetricos_adolescentes = parse_float(data.get("eventos_obstetricos_adolescentes"))

            # Días de estancia por servicio
            dias_est_med = parse_float(data.get("dias_est_med") or data.get("dias_estancia_med_interna"))
            dias_est_cir = parse_float(data.get("dias_est_cir") or data.get("dias_estancia_cirugia"))
            dias_est_ped = parse_float(data.get("dias_est_ped") or data.get("dias_estancia_pediatria"))
            dias_est_gin = parse_float(data.get("dias_est_gin") or data.get("dias_estancia_ginecobstetricia"))
            dias_est_otr = parse_float(data.get("dias_est_otros") or data.get("dias_estancia_otros"))

            # Egresos por servicio
            egresos_med = parse_float(data.get("egre_med_interna") or data.get("med_interna"))
            egresos_cir = parse_float(data.get("egre_cirugia") or data.get("cirugia"))
            egresos_ped = parse_float(data.get("egre_pediatria") or data.get("pediatria"))
            egresos_gin = parse_float(data.get("egre_gineco") or data.get("ginecobstetricia"))
            egresos_otr = parse_float(data.get("egre_otros") or data.get("otros"))

            # Promedios de Estancia
            v_med = round(dias_est_med / egresos_med, 2) if egresos_med > 0 else 0.0
            v_cir = round(dias_est_cir / egresos_cir, 2) if egresos_cir > 0 else 0.0
            v_ped = round(dias_est_ped / egresos_ped, 2) if egresos_ped > 0 else 0.0
            v_gin = round(dias_est_gin / egresos_gin, 2) if egresos_gin > 0 else 0.0
            v_otr = round(dias_est_otr / egresos_otr, 2) if egresos_otr > 0 else 0.0

            urgencias_tot = parse_float(data.get("urgencias") or data.get("total_u"))

            return {
                # KPIs Operativos (Productividad Diaria)
                "consultas_por_dia": round(parse_float(data.get("consultas")) / dias_val, 2),
                "especialidad_por_dia": round(parse_float(data.get("especialidad")) / dias_val, 2),
                "urgencias_por_dia": round(urgencias_tot / dias_val, 2),
                "porcentaje_calificada": round((parse_float(data.get("calificada")) / urgencias_tot) * 100.0, 2) if urgencias_tot > 0 else 0.0,
                "nacimientos_por_dia": round(nacimientos / dias_val, 2),
                "porcentaje_cesareas": round((parse_float(data.get("nac_cesarea")) / nacimientos) * 100.0, 2) if nacimientos > 0 else 0.0,
                "prom_inter_diarias_qx": round(parse_float(data.get("total_proced_dentro")) / (quirofanos * dias_val), 2) if (quirofanos > 0 and dias_val > 0) else 0.0,
                "porcentaje_apeo": round((parse_float(data.get("apeo") or data.get("total_apeo")) / eventos) * 100.0, 2) if eventos > 0 else 0.0,
                "porcentaje_adolescente_apeo": round((adolescente_apeo * 100.0) / eventos_obstetricos_adolescentes, 2) if eventos_obstetricos_adolescentes > 0 else 0.0,

                # Ocupación Porcentual
                "porcentaje_ocupacion": calcular_ocupacion(data.get("dias_p"), data.get("dias_cama_total")),
                "porcentaje_ocupacion_med_interna": calcular_ocupacion(data.get("dias_p_med_int"), data.get("dias_cama_med")),
                "porcentaje_ocupacion_cirugia": calcular_ocupacion(data.get("dias_p_cirugia"), data.get("dias_cama_cir")),
                "porcentaje_ocupacion_pediatria": calcular_ocupacion(data.get("dias_p_pediatria"), data.get("dias_cama_ped")),
                "porcentaje_ocupacion_gineco": calcular_ocupacion(data.get("dias_p_gineco"), data.get("dias_cama_gin")),
                "porcentaje_ocupacion_otros": calcular_ocupacion(data.get("dias_p_otros"), data.get("dias_cama_otros")),

                # Estancias Promedio
                "prom_dias_estancia": round(parse_float(data.get("dias_estancia")) / egresos, 2) if egresos > 0 else 0.0,
                "prom_dias_estancia_med_interna": v_med,
                "prom_dias_estancia_cirugia": v_cir,
                "prom_dias_estancia_pediatria": v_ped,
                "prom_dias_estancia_gineco": v_gin,
                "prom_dias_estancia_otros": v_otr,

                # Rotación e Intervalo de Sustitución
                "indice_rotacion": round(egresos / camas, 2) if camas > 0 else 0.0,
                "interv_sustitucion": round((((camas * dias_val) - parse_float(data.get("dias_p"))) / egresos), 2) if egresos > 0 else 0.0,

                # Mortalidad
                "mortalidad_cruda": round((parse_float(data.get("egre_defunciones")) * 1000.0) / egresos, 2) if egresos > 0 else 0.0,
                "mortalidad_ajustada": round((parse_float(data.get("egre_defunciones_48h")) * 1000.0) / parse_float(data.get("total_egresos_48h")), 2) if parse_float(data.get("total_egresos_48h")) > 0 else 0.0,
            }
        
        #PARTE 5
        # ==========================================================
        # RECORRER ROWS
        # ==========================================================  
        DEPENDENCIAS_KPIS = {
            # --- PRODUCTIVIDAD DIARIA ---
            "consultas_por_dia": ["consultas"],
            "especialidad_por_dia": ["especialidad"],
            "urgencias_por_dia": ["urgencias", "total_u"],
            "nacimientos_por_dia": ["total_nacimientos", "nacimientos"],
    
            # --- APEO Y SALUD MATERNA ---
            "porcentaje_apeo": ["apeo", "total_apeo", "eventos_obstetricos", "total_nacimientos", "nacimientos", "abortos"],
            "porcentaje_adolescente_apeo": ["adolescente_apeo", "eventos_obstetricos_adolescentes"],
            "porcentaje_cesareas": ["nac_cesarea", "total_nacimientos", "nacimientos"],
    
            # --- MORTALIDAD ---
            "mortalidad_cruda": ["egre_defunciones", "defunciones", "total_egresos"],
            "mortalidad_ajustada": ["egre_defunciones_48h", "defunciones_48h", "total_egresos_48h", "egresos_48h"],
    
            # --- OCUPACIÓN ---
            "porcentaje_ocupacion": ["dias_p", "dias_cama_total"],
            "porcentaje_ocupacion_med_interna": ["dias_p_med_int", "dias_cama_med"],
            "porcentaje_ocupacion_cirugia": ["dias_p_cirugia", "dias_cama_cir"],
            "porcentaje_ocupacion_pediatria": ["dias_p_pediatria", "dias_cama_ped"],
            "porcentaje_ocupacion_gineco": ["dias_p_gineco", "dias_cama_gin"],
            "porcentaje_ocupacion_otros": ["dias_p_otros", "dias_cama_otros"],
    
            # --- ESTANCIA Y ROTACIÓN ---
            "prom_dias_estancia": ["dias_estancia", "dias_estancia_sum", "total_egresos"],
            "prom_dias_estancia_med_interna": ["dias_est_med", "dias_estancia_med_interna", "egre_med_interna", "med_interna"],
            "prom_dias_estancia_cirugia": ["dias_est_cir", "dias_estancia_cirugia", "egre_cirugia", "cirugia"],
            "prom_dias_estancia_pediatria": ["dias_est_ped", "dias_estancia_pediatria", "egre_pediatria", "pediatria"],
            "prom_dias_estancia_gineco": ["dias_est_gin", "dias_estancia_ginecobstetricia", "egre_gineco", "ginecobstetricia"],
            "prom_dias_estancia_otros": ["dias_est_otros", "dias_estancia_otros", "egre_otros", "otros"],
            "indice_rotacion": ["total_egresos", "camas_total"],
            "interv_sustitucion": ["camas_total", "dias_p", "total_egresos"],
    
            # --- URGENCIAS Y QUIRÓFANO ---
            "porcentaje_calificada": ["calificada", "urgencias", "total_u"],
            "prom_inter_diarias_qx": ["total_proced_dentro", "cirugias", "quirofanos"]
        }

        indicadores_solicitados_raw = request.args.getlist("indicadores[]") or request.args.getlist("indicadores")
        indicadores_solicitados_set = {str(i).lower().strip() for i in indicadores_solicitados_raw}

        # 🔑 DETECTAR INSUMOS DEPENDIENTES DE FORMA LIMPIA
        insumos_necesarios = set()
        for ind_req in indicadores_solicitados_set:
            if ind_req in DEPENDENCIAS_KPIS:
                insumos_necesarios.update({str(dep).lower().strip() for dep in DEPENDENCIAS_KPIS[ind_req]})

        # 🟢 FIX 1: PROCESAR BUCLE DE ROWS_E UNA SOLA VEZ (ELIMINADO BUCLE DUPLICADO)
        for r in rows_e:
            anio = int(r["anio"])
            mes = int(r["mes"]) if r.get("mes") is not None else 13
            unidad = r.get("nombre_unidad", "TOTAL GENERAL")
            clues_val = r.get("clues", "TOTAL")

            base = {
                field.lower(): parse_float(r.get(field))
                for field in SUM_FIELDS + list(indicadores_max)
            }

            if mes != 13:
                dias = calendar.monthrange(anio, mes)[1]
            else:
                dias = (
                    sum(calendar.monthrange(anio, m)[1] for m in meses_validos)
                    if meses_validos else 365
                )

            kpis = calcular_kpis(base, dias)
            dataset = {**base, **kpis}

            for indicador, valor in dataset.items():
                indicador_norm = str(indicador).lower().strip()

                if (
                    es_descarga_masiva
                    or indicador_norm in indicadores_solicitados_set
                    or indicador_norm in insumos_necesarios
                ):
                    data_acumulada.append({
                        "anio": anio,
                        "mes": mes,
                        "clues": clues_val,
                        "nombre_unidad": unidad,
                        "tipologia": r.get("tipologia", "TODAS"),
                        "indicador": indicador_norm,
                        "valor": round(parse_float(valor), 2),
                    })

    # ======================================================
    # PROCESAMIENTO VISTA UNIFICADA (VW_INDICADORES_UNIFICADOS)
    # ======================================================
    indicadores_ya_calculados = {field.lower() for field in SUM_FIELDS + list(indicadores_max)}
    grupos = request.args.getlist("grupos[]") or request.args.getlist("grupos")

    es_consulta_grupo = (
        not unidades 
        or "TODAS" in [g.upper() for g in grupos] 
        or any("GRUPO_" in g.upper() for g in grupos)
    )

    quiere_vistas = bool(unidades) or bool(grupos) or es_consulta_grupo or bool(insumos_necesarios)

    if quiere_vistas:
        params_v = []

        # 🟢 FIX 2: MANTENER CLUES Y UNIDADES REALES PARA PERMITIR SEGMENTACIÓN MULTIGRUPO
        query_v = """
        SELECT
            v.mes,
            LOWER(v.indicador) AS indicador,
            v.anio,
            v.clues,
            COALESCE(c.nombre_unidad, v.nombre_unidad) AS nombre_unidad,
            COALESCE(c.tipologia, 'TODAS') AS tipologia,
            SUM(CAST(COALESCE(v.valor, 0) AS DECIMAL(15,2))) AS valor
        FROM vw_indicadores_unificados v
        LEFT JOIN catalogo_unidades c ON v.clues = c.clues
        WHERE 1=1
        """

        if unidades and not es_consulta_grupo:
            query_v += " AND v.clues IN ({})".format(",".join(["%s"] * len(unidades)))
            params_v.extend(unidades)

        if anios:
            query_v += " AND v.anio IN ({})".format(",".join(["%s"] * len(anios)))
            params_v.extend(anios)

        if not es_descarga_masiva:
            indicadores_a_buscar = list(indicadores_solicitados_set.union(insumos_necesarios))
            if indicadores_a_buscar:
                query_v += " AND LOWER(v.indicador) IN ({})".format(
                    ",".join(["%s"] * len(indicadores_a_buscar))
                )
                params_v.extend(indicadores_a_buscar)

        query_v += " GROUP BY v.mes, v.indicador, v.anio, v.clues, COALESCE(c.nombre_unidad, v.nombre_unidad), COALESCE(c.tipologia, 'TODAS')"

        cur.execute(query_v, params_v)
        rows_v = cur.fetchall()

        # ======================================================
        # FILTRADO DE MESES Y GENERACIÓN DE JSON
        # ======================================================
        meses_con_produccion_real = sorted(
            list({
                int(r["mes"]) 
                for r in rows_e 
                if r.get("mes") is not None and int(r.get("mes")) in range(1, 13)
            })
        )

        if meses and 13 not in meses:
            meses_a_permitir = meses
        elif meses_con_produccion_real:
            meses_a_permitir = meses_con_produccion_real
        else:
            meses_a_permitir = meses_validos

        vista_cache = {}

        for row in rows_v:
            mes = int(row["mes"])

            if meses_a_permitir and mes not in meses_a_permitir:
                continue

            indicador = str(row["indicador"]).strip().lower()
            key = (row["anio"], row["clues"], row["nombre_unidad"], row.get("tipologia", "TODAS"), indicador)
            valor = parse_float(row["valor"])

            if es_anual:
                if key not in vista_cache:
                    vista_cache[key] = valor
                else:
                    if indicador in indicadores_max or indicador in RECURSOS_FISICOS or indicador in indicadores_equipo_medico:
                        # 🟢 FIX 3: MÁXIMO O PROMEDIO PARA RECURSOS EN VISTA ANUAL
                        vista_cache[key] = max(vista_cache[key], valor)
                    else:
                        vista_cache[key] += valor
            else:
                data_acumulada.append({
                    "anio": row["anio"],
                    "mes": mes,
                    "clues": row["clues"],
                    "nombre_unidad": row["nombre_unidad"],
                    "tipologia": row.get("tipologia", "TODAS"),
                    "indicador": indicador,
                    "valor": round(valor, 2),
                })

        # ======================================================
        # GENERACIÓN DE REGISTROS ANUALES (MES 13)
        # ======================================================
        if es_anual:
            for (anio, clues, unidad, tipologia, indicador), valor in vista_cache.items():
                if indicador in indicadores_ya_calculados:
                    continue

                data_acumulada.append({
                    "anio": anio,
                    "mes": 13,
                    "clues": clues,
                    "nombre_unidad": unidad,
                    "tipologia": tipologia,
                    "indicador": indicador,
                    "valor": round(valor, 2),
                })


    # PARTE 6
  
   # ==========================================================
    # PROCESAMIENTO DE TABLAS ESTÁTICAS (CAMAS NO CENSABLES Y EQUIPO)
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

    # Ejecución segura de consultas estáticas
    if callable(globals().get("procesar_tabla_estatica")):
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
    # TOTAL GENERAL Y FILTRADO SEGÚN MODO DE AGRUPACIÓN (MULTIGRUPO)
    # ==========================================================
    if modo_agrupacion == "acumulado":
        # 🔑 1. OBTENER LISTA DE GRUPOS SOLICITADOS EN LA URL
        grupos_solicitados = request.args.getlist("grupos[]") or request.args.getlist("grupos")
        
        etiquetas_grupos = {
            "TODAS": "TODAS LAS UNIDADES (42)",
            "HG": "Hospitales Generales (HG)",
            "HC": "Hospitales Comunitarios (HC)",
            "HE": "Hospitales de Especialidad (HE)"
        }

        if not grupos_solicitados:
            grupos_solicitados = list({r.get("tipologia", "TODAS") for r in data_acumulada if r.get("tipologia")})

        data_multigrupo = []

        # 🔑 2. SEGMENTAR CADA GRUPO INDEPENDIENTEMENTE SIN FALLBACKS DISTORSIONADOS
        for id_grupo in grupos_solicitados:
            id_grupo_upper = str(id_grupo).upper().strip()
            
            # Obtener CLUES enviadas explícitamente para este grupo
            clues_grupo = set(request.args.getlist(f"grupo_{id_grupo_upper}_clues[]"))

            if clues_grupo:
                data_subgrupo = [r for r in data_acumulada if r.get("clues") in clues_grupo]
            elif id_grupo_upper == "TODAS":
                data_subgrupo = [r for r in data_acumulada if r.get("clues") != "TOTAL"]
            else:
                data_subgrupo = [r for r in data_acumulada if str(r.get("tipologia")).upper() == id_grupo_upper]

            # 🟢 FIX: Si un grupo no contiene datos para los filtros, omitirlo limpiamente en lugar de duplicar 'data_acumulada'
            if not data_subgrupo:
                continue

            # Generar el total exclusivo para este grupo
            totales_grupo = generar_total_general(
                data_acumulada=data_subgrupo,
                meses_validos=meses_validos,
                SUM_FIELDS=SUM_FIELDS,
                MAX_FIELDS=MAX_FIELDS,
                indicadores_max=indicadores_max,
                calcular_kpis=calcular_kpis,
                es_descarga_masiva=es_descarga_masiva,
                indicadores_solicitados=indicadores_solicitados,
            )

            # 🔑 3. ASIGNAR NOMBRE ÚNICO A CADA GRUPO PARA SEPARAR LÍNEAS EN CHART.JS
            nombre_etiqueta = etiquetas_grupos.get(id_grupo_upper, f"GRUPO {id_grupo_upper}")
            for t in totales_grupo:
                t["nombre_unidad"] = nombre_etiqueta
                t["clues"] = f"GRUPO_{id_grupo_upper}"
                data_multigrupo.append(t)

        if data_multigrupo:
            data_acumulada = data_multigrupo

    elif len(unidades) > 1:
        # 🏥 MODO INDIVIDUAL MULTI-UNIDAD:
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
    # CIERRE DE CURSOR Y ORDENAMIENTO DE RESPUESTA JSON
    # ==========================================================
    try:
        cur.close()
    except Exception:
        pass

    # 🟢 FIX: ORDENAMIENTO ROBUSTO Y NORMALIZADO PREVINIENDO DESFASES EN CHART.JS
    data_acumulada.sort(
        key=lambda x: (
            int(x.get("anio") or 0),
            str(x.get("nombre_unidad") or ""),
            int(x.get("mes")) if (x.get("mes") is not None and str(x.get("mes")).isdigit()) else 13,
            str(x.get("indicador") or ""),
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

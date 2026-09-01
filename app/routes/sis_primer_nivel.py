from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required
from flask_mysqldb import MySQLdb
from app import mysql

# Blueprint para SIS Primer Nivel
sis_pn = Blueprint('sis_pn', __name__, url_prefix='/sis_primer_nivel')


@sis_pn.route("/")
@login_required
def dashboard_sis_primer_nivel():
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    # 1. Consulta principal de registros SIS (Asegúrate que la tabla tenga las columnas jurisdiccion y municipio)
    query = """
        SELECT 
            anio,
            mes,
            clues,
            nombre_unidad,
            jurisdiccion,
            municipio,
            consultas,
            mental,
            bucal,
            embarazadas,
            planificacion_familiar,
            detecciones,
            tamiz
        FROM sis_registros_agregados_primer_nivel
        ORDER BY anio, mes, clues
    """
    cursor.execute(query)
    resultados = cursor.fetchall()

    # 2. Extracción de Catálogos Únicos para poblar el Sidebar y los Popovers de Filtro
    anios_disponibles = sorted({r["anio"] for r in resultados if r["anio"]}) if resultados else []
    
    # Lista de dicts para Unidades (CLUES y Nombre)
    unidades_unicas = {}
    for r in resultados:
        if r["clues"] and r["clues"] not in unidades_unicas:
            unidades_unicas[r["clues"]] = r["nombre_unidad"]
    unidades_disponibles = [{"clues": k, "nombre": v} for k, v in sorted(unidades_unicas.items(), key=lambda x: x[1])]

    # Listas simples de Jurisdicciones y Municipios ordenadas
    jurisdicciones_disponibles = sorted({r["jurisdiccion"] for r in resultados if r.get("jurisdiccion")}) if resultados else []
    municipios_disponibles = sorted({r["municipio"] for r in resultados if r.get("municipio")}) if resultados else []

    # 3. Consulta de control de estatus
    cursor.execute("""
        SELECT anio, estatus_inicio, fecha_actualizacion, estatus
        FROM sis_control_anual
        ORDER BY anio
    """)
    control_anual = cursor.fetchall()

    cursor.close()

    return render_template(
        "sis/reporte_sis_primer_nivel.html",
        resultados=resultados,
        anios_disponibles=anios_disponibles,
        unidades_disponibles=unidades_disponibles,
        jurisdicciones_disponibles=jurisdicciones_disponibles,
        municipios_disponibles=municipios_disponibles,
        control_anual=control_anual,
        tipo="sis",
        title="Reporte SIS - Primer Nivel"
    )


# ======================================================
# API ENDPOINT (Para peticiones AJAX de filtros en vivo)
# ======================================================
@sis_pn.route("/api/filtrar", methods=["POST"])
@login_required
def filtrar_datos_sis():
    data = request.get_json() or {}

    agrupar_por = data.get("agrupar_por", "clues") # clues | jurisdiccion | municipio
    unidades = data.get("unidades", [])
    jurisdicciones = data.get("jurisdicciones", [])
    municipios = data.get("municipios", [])

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    query_base = """
        SELECT 
            anio, mes, clues, nombre_unidad, jurisdiccion, municipio,
            consultas, mental, bucal, embarazadas, planificacion_familiar, detecciones, tamiz
        FROM sis_registros_agregados_primer_nivel
        WHERE 1=1
    """
    params = []

    # Aplicación de filtros según el nivel de agrupación activo
    if agrupar_por == "clues" and unidades:
        query_base += f" AND clues IN ({','.join(['%s'] * len(unidades))})"
        params.extend(unidades)
    elif agrupar_por == "jurisdiccion" and jurisdicciones:
        query_base += f" AND jurisdiccion IN ({','.join(['%s'] * len(jurisdicciones))})"
        params.extend(jurisdicciones)
    elif agrupar_por == "municipio" and municipios:
        query_base += f" AND municipio IN ({','.join(['%s'] * len(municipios))})"
        params.extend(municipios)

    query_base += " ORDER BY anio, mes"

    cursor.execute(query_base, params)
    datos_filtrados = cursor.fetchall()
    cursor.close()

    return jsonify({"status": "success", "data": datos_filtrados})
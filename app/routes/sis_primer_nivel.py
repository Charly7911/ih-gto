from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required
from flask_mysqldb import MySQLdb
from app import mysql

sis_pn = Blueprint('sis_pn', __name__, url_prefix='/sis_primer_nivel')


@sis_pn.route("/")
@login_required
def dashboard_sis_primer_nivel():
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

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
    resultados = cursor.fetchall() or []

    # 1. Catálogo de Años
    anios_disponibles = sorted({r["anio"] for r in resultados if r.get("anio")}, reverse=True)
    
    # 2. Catálogo de Unidades (Lista simple ordenada de nombres/CLUES)
    unidades_disponibles = sorted({r["nombre_unidad"] for r in resultados if r.get("nombre_unidad")})

    # 3. Catálogo de Jurisdicciones y Municipios
    jurisdicciones_disponibles = sorted({str(r["jurisdiccion"]) for r in resultados if r.get("jurisdiccion") is not None})
    municipios_disponibles = sorted({r["municipio"] for r in resultados if r.get("municipio")})

    # 4. Control Anual
    cursor.execute("""
        SELECT anio, estatus_inicio, fecha_actualizacion, estatus
        FROM sis_control_anual
        ORDER BY anio
    """)
    control_anual = cursor.fetchall() or []

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


@sis_pn.route("/api/filtrar", methods=["POST"])
@login_required
def filtrar_datos_sis():
    data = request.get_json() or {}

    unidades = data.get("unidades", [])
    jurisdicciones = data.get("jurisdicciones", [])
    municipios = data.get("municipios", [])
    anios = data.get("anios", [])
    meses = data.get("meses", [])

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    query_base = """
        SELECT 
            anio, mes, clues, nombre_unidad, jurisdiccion, municipio,
            consultas, mental, bucal, embarazadas, planificacion_familiar, detecciones, tamiz
        FROM sis_registros_agregados_primer_nivel
        WHERE 1=1
    """
    params = []

    # Evaluaciones independientes para permitir combinación cruzada de filtros
    if unidades:
        query_base += f" AND (clues IN ({','.join(['%s'] * len(unidades))}) OR nombre_unidad IN ({','.join(['%s'] * len(unidades))}))"
        params.extend(unidades + unidades)
        
    if jurisdicciones:
        query_base += f" AND jurisdiccion IN ({','.join(['%s'] * len(jurisdicciones))})"
        params.extend(jurisdicciones)
        
    if municipios:
        query_base += f" AND municipio IN ({','.join(['%s'] * len(municipios))})"
        params.extend(municipios)

    if anios:
        query_base += f" AND anio IN ({','.join(['%s'] * len(anios))})"
        params.extend(anios)

    if meses:
        query_base += f" AND mes IN ({','.join(['%s'] * len(meses))})"
        params.extend(meses)

    query_base += " ORDER BY anio, mes"

    cursor.execute(query_base, params)
    datos_filtrados = cursor.fetchall() or []
    cursor.close()

    return jsonify({"status": "success", "data": datos_filtrados})
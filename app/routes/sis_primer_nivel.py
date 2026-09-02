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
            anio, mes, clues, nombre_unidad, jurisdiccion, municipio,
            consultas, mental, bucal, embarazadas, planificacion_familiar, detecciones, tamiz
        FROM sis_registros_agregados_primer_nivel
        ORDER BY anio, mes, clues
    """
    cursor.execute(query)
    resultados = cursor.fetchall() or []

    # 1. Catálogo de Años
    anios_disponibles = sorted({r["anio"] for r in resultados if r.get("anio")}, reverse=True)
    
    # 2. Catálogo de Unidades
    unidades_disponibles = sorted({r["nombre_unidad"] for r in resultados if r.get("nombre_unidad")})

    # 3. Catálogo de Jurisdicciones
    jurisdicciones_disponibles = sorted({str(r["jurisdiccion"]) for r in resultados if r.get("jurisdiccion") is not None})

    # 3.1 Catálogo de Municipios CON JURISDICCIÓN
    municipios_set = {
        (r["municipio"], str(r["jurisdiccion"])) 
        for r in resultados 
        if r.get("municipio") and r.get("jurisdiccion") is not None
    }
    
    municipios_disponibles = sorted(
        [{"nombre": mun, "jurisdiccion": jur} for mun, jur in municipios_set],
        key=lambda x: x["nombre"]
    )

    # 4. Control Anual (CONVERSIÓN DE FECHA A TEXTO PARA EVITAR ERROR 500)
    cursor.execute("""
        SELECT anio, estatus_inicio, fecha_actualizacion, estatus
        FROM sis_control_anual
        ORDER BY anio
    """)
    rows_control = cursor.fetchall() or []
    control_anual = []
    for row in rows_control:
        if row.get("fecha_actualizacion"):
            row["fecha_actualizacion"] = str(row["fecha_actualizacion"])
        control_anual.append(row)

    # 5. CATÁLOGO DE VARIABLES
    cursor.execute("""
        SELECT modulo, variable, descripcion, apartado, descripcion_apartado
        FROM catalogo_variables
        ORDER BY modulo, apartado, variable
    """)
    filas_catalogo = cursor.fetchall() or []

    catalogo_estructurado = {}

    for row in filas_catalogo:
        mod = row.get("modulo") or "varios"
        apt = str(row.get("apartado") or "00")
        desc_apt = row.get("descripcion_apartado") or "Sin Descripción"
        code = row.get("variable")
        nombre_var = row.get("descripcion") or code

        if mod not in catalogo_estructurado:
            catalogo_estructurado[mod] = {}

        if apt not in catalogo_estructurado[mod]:
            catalogo_estructurado[mod][apt] = {
                "apartado": apt,
                "descripcion_apartado": desc_apt,
                "variables": []
            }

        catalogo_estructurado[mod][apt]["variables"].append({
            "codigo": code,
            "nombre": nombre_var
        })

    # Convertimos los apartados de cada módulo a lista
    catalogo_variables = {
        mod: list(apartados.values()) 
        for mod, apartados in catalogo_estructurado.items()
    }

    cursor.close()

    return render_template(
        "sis/reporte_sis_primer_nivel.html",
        resultados=resultados,
        anios_disponibles=anios_disponibles,
        unidades_disponibles=unidades_disponibles,
        jurisdicciones_disponibles=jurisdicciones_disponibles,
        municipios_disponibles=municipios_disponibles,
        control_anual=control_anual,
        catalogo_variables=catalogo_variables,
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
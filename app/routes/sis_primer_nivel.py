from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required
from flask_mysqldb import MySQLdb
from app import mysql

sis_pn = Blueprint('sis_pn', __name__, url_prefix='/sis_primer_nivel')

def obtener_modulo_por_apartado(apartado_raw, variable_code=""):
    """
    Relaciona el número de apartado oficial del SIS con las opciones del <select id="filtroSisDetalle">:
    'consultas', 'embarazadas', 'mental', 'bucal', 'tamiz', 'planificacion_familiar', 'detecciones'
    """
    apt = str(apartado_raw or "").strip().zfill(2)
    var = str(variable_code or "").upper()

    # Evaluación por número de apartado o prefijo directo
    if apt in ["1", "215"]:
        return "consultas"
    elif apt in ["24"] or var.startswith("EMB"):
        return "embarazadas"
    elif apt in ["36"] or var.startswith(("PFC", "PLA")):
        return "planificacion_familiar"
    elif apt in ["56"] or var.startswith(("DET", "DTO")):
        return "detecciones"
    elif apt in ["111"] or var.startswith(("RNL", "TAM")):
        return "tamiz"
    elif apt in ["2","215"] or var.startswith("ODONT"):
        return "bucal"
    elif apt in ["2"] or var.startswith("PSIC"):
        return "mental"
    else:
        return "consultas"  # Módulo por defecto


@sis_pn.route("/")
@login_required
def dashboard_sis_primer_nivel():
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    try:
        # 1. Consulta Principal
        query = """
            SELECT 
                anio, mes, clues, nombre_unidad, jurisdiccion, municipio,
                consultas, mental, bucal, embarazadas, planificacion_familiar, detecciones, tamiz
            FROM sis_registros_agregados_primer_nivel
            ORDER BY anio, mes, clues
        """
        cursor.execute(query)
        resultados = cursor.fetchall() or []

        # Catálogos auxiliares para la vista
        anios_disponibles = sorted({r["anio"] for r in resultados if r.get("anio")}, reverse=True)
        unidades_disponibles = sorted({r["nombre_unidad"] for r in resultados if r.get("nombre_unidad")})
        jurisdicciones_disponibles = sorted({str(r["jurisdiccion"]) for r in resultados if r.get("jurisdiccion") is not None})

        municipios_set = {
            (r["municipio"], str(r["jurisdiccion"])) 
            for r in resultados 
            if r.get("municipio") and r.get("jurisdiccion") is not None
        }
        municipios_disponibles = sorted(
            [{"nombre": mun, "jurisdiccion": jur} for mun, jur in municipios_set],
            key=lambda x: x["nombre"]
        )

        # 2. Control Anual (Serialización de fechas a String para evitar Error 500)
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

        # 3. Catálogo de Variables
        cursor.execute("""
            SELECT apartado, descripcion_apartado, variable, descripcion
            FROM catalogo_variables
            ORDER BY apartado, variable
        """)
        filas_catalogo = cursor.fetchall() or []

        catalogo_estructurado = {}

        for row in filas_catalogo:
            code = row.get("variable")
            apt = str(row.get("apartado") or "00")
            desc_apt = row.get("descripcion_apartado") or "Sin Descripción"
            nombre_var = row.get("descripcion") or code

            # Asignación del módulo correspondiente
            mod = obtener_modulo_por_apartado(apt, code)

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

        # Estructura final requerida por el JS del frontend
        catalogo_variables = {
            mod: list(apartados.values()) 
            for mod, apartados in catalogo_estructurado.items()
        }

    finally:
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

    try:
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
    finally:
        cursor.close()

    return jsonify({"status": "success", "data": datos_filtrados})
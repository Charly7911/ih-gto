from flask import Blueprint, jsonify, render_template, request
from flask_mysqldb import MySQLdb
from flask_login import login_required
from app import mysql

urgencias = Blueprint('urgencias', __name__, url_prefix='/urgencias')

# ------------------------------------------------------
# RUTA PRINCIPAL AL DAR CLIC EN "URGECIAS" DEL MENÚ
# ------------------------------------------------------
@urgencias.route('/')
@login_required
def inicio_urgencias():

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    cursor.execute("""
        SELECT DISTINCT anio
        FROM urgencias_agregado
        ORDER BY anio
    """)
    anios_disponibles = [row["anio"] for row in cursor.fetchall()]

    cursor.execute("""
        SELECT DISTINCT nombre_unidad
        FROM urgencias_agregado
        ORDER BY nombre_unidad
    """)
    unidades_disponibles = [row["nombre_unidad"] for row in cursor.fetchall()]

    cursor.execute("""
        SELECT anio, estatus_inicio, fecha_actualizacion, estatus
        FROM urgencias_control_anual
        ORDER BY anio
    """)
    control_anual = cursor.fetchall()

    cursor.close()

    return render_template(
        'urgencias/reporte_urgencias.html',
        anios_disponibles=anios_disponibles,
        unidades_disponibles=unidades_disponibles,
        control_anual=control_anual,
        title="Reporte de Urgencias"
    )





# ------------------------------------------------------
# API PARA TABLAS Y GRÁFICAS
# ------------------------------------------------------

@urgencias.route('/api/reporte_urgencias')
@login_required 
def obtener_datos_urgencias():

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    meses_str = request.args.get('meses')
    anios_str = request.args.get('anios')
    unidades_str = request.args.get("unidades")

    meses = meses_str.split(',') if meses_str else []
    anios = anios_str.split(',') if anios_str else []
    unidades = unidades_str.split(',') if unidades_str else []

    filtros = []
    valores = []

    if meses:
        filtros.append(f"mes_estadistico IN ({','.join(['%s']*len(meses))})")
        valores.extend(meses)

    if anios:
        filtros.append(f"anio IN ({','.join(['%s']*len(anios))})")
        valores.extend(anios)

    if unidades:
        filtros.append(f"nombre_unidad IN ({','.join(['%s']*len(unidades))})")
        valores.extend(unidades)

    query = """
        SELECT
            clues AS CLUES,
            nombre_unidad AS Hospital,
            anio AS Anio,
            SUM(calificada) AS Calificada,
            SUM(no_calificada) AS No_Calificada,
            SUM(accidentes) AS Accidentes,
            SUM(medica) AS Medica,
            SUM(ginecobstetricia) AS Ginecobstetricia,
            SUM(pediatrica) AS Pediatrica,
            SUM(no_especificado) AS No_Especificado,
            SUM(total) AS Total,
            ROUND(SUM(calificada) / NULLIF(SUM(total),0) * 100,1) AS Porcentaje_Calificada
        FROM urgencias_agregado
    """

    if filtros:
        query += " WHERE " + " AND ".join(filtros)

    query += """
        GROUP BY clues, nombre_unidad, anio
        ORDER BY nombre_unidad, anio
    """

    cursor.execute(query, valores)
    resultados = cursor.fetchall()
    cursor.close()

    return jsonify(resultados)


@urgencias.route('/api/urgencias_por_mes')
@login_required 
def urgencias_por_mes():

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    meses = request.args.get('meses', '').split(',')
    anios = request.args.get('anios', '').split(',')
    unidades = request.args.get('unidades', '').split(',')
    motivo = request.args.get('motivo', 'todas')

    filtros = []
    valores = []

    if meses and meses != ['']:
        filtros.append(f"mes_estadistico IN ({','.join(['%s']*len(meses))})")
        valores.extend(meses)

    if anios and anios != ['']:
        filtros.append(f"anio IN ({','.join(['%s']*len(anios))})")
        valores.extend(anios)

    if unidades and unidades != ['']:
        filtros.append(f"nombre_unidad IN ({','.join(['%s']*len(unidades))})")
        valores.extend(unidades)

    # 👉 columna a sumar según motivo
    campo_suma = "total"
    if motivo == "Medica":
        campo_suma = "medica"
    elif motivo == "Accidentes":
        campo_suma = "accidentes"
    elif motivo == "Pediatrica":
        campo_suma = "pediatrica"
    elif motivo == "Ginecobstetricia":
        campo_suma = "ginecobstetricia"

    query = f"""
        SELECT
            nombre_unidad AS Unidad,
            anio AS Anio,
            mes_estadistico AS Mes,
            SUM({campo_suma}) AS Total
        FROM urgencias_agregado
    """

    if filtros:
        query += " WHERE " + " AND ".join(filtros)

    query += """
        GROUP BY nombre_unidad, anio, mes_estadistico
        ORDER BY nombre_unidad, anio, mes_estadistico
    """

    cursor.execute(query, valores)
    data = cursor.fetchall()
    cursor.close()

    return jsonify(data)

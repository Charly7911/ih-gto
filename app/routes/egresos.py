import MySQLdb
from flask import Blueprint, request, jsonify, render_template
from flask_login import login_required
from app.controllers.egresos_controller import obtener_indicador
from app import mysql

egresos = Blueprint('egresos', __name__, url_prefix='/egresos')

@egresos.route('/indicadores')
def indicadores_page():

    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    # 🔹 Años disponibles
    cur.execute("""
        SELECT DISTINCT anio
        FROM egresos_agregado
        ORDER BY anio DESC
    """)
    anios = [r["anio"] for r in cur.fetchall()]

    # 🔹 Unidades disponibles
    cur.execute("""
        SELECT DISTINCT c.nombre_unidad AS unidad
        FROM egresos_agregado e
        LEFT JOIN catalogo_unidades c ON e.clues = c.clues
        ORDER BY unidad ASC
    """)
    unidades = [r["unidad"] for r in cur.fetchall()]

    # 🔹 Control anual EGRESOS
    cur.execute("""
        SELECT anio, estatus_inicio, fecha_actualizacion, estatus
        FROM seul_control_anual
        ORDER BY anio
    """)
    control_anual = cur.fetchall()

    cur.close()

    return render_template(
        'egresos/reporte_egresos.html',
        anios_disponibles=anios,
        unidades_disponibles=unidades,
        control_anual=control_anual,
        title="Reporte Egresos"
    )


# Endpoint universal para consultar cualquier indicador:
@egresos.route('/indicador/<nombre>', methods=['GET'])
def indicador_egresos(nombre):
    meses = request.args.get('meses')     # ej: "1,2,3"
    tipologias = request.args.get('tipologias')  # ej: "1,2"
    anio = request.args.get('anios')       # ej: "2024"

    datos = obtener_indicador(nombre, meses, tipologias, anio)
    return jsonify(datos)

# Endpoint universal basado en indicador seleccionado
@egresos.route('/api/indicadores')
def api_indicadores():

    indicador = request.args.get("indicador")
    meses = request.args.get("meses", "")
    anio = request.args.get("anios", "")
    unidades = request.args.get("unidades", "")
    modo = request.args.get("modo", "tabla") 
   

    meses_list = meses.split(",") if meses else []
    unidades_list = unidades.split(",") if unidades else []

    datos = obtener_indicador(
        nombre=indicador,
        meses=meses_list,
        tipologias="",
        anio=anio, 
        unidades=unidades_list,   # 👈 lista real
        modo=modo
    )

    return jsonify(datos)


@egresos.route('/api/camas_censables')
def camas_censables():

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    anios = request.args.get('anios', '').split(',')
    unidades = request.args.get('unidades', '').split(',')

    filtros = []
    valores = []

    if anios and anios != ['']:
        filtros.append(f"s.anio IN ({','.join(['%s']*len(anios))})")
        valores.extend(anios)

    if unidades and unidades != ['']:
        filtros.append(f"s.clues IN ({','.join(['%s']*len(unidades))})")
        valores.extend(unidades)

    query = """
        SELECT
            s.anio,
            s.clues,
            SUM(s.med_int)   AS Med_Interna,
            SUM(s.cirugia)   AS Cirugia,
            SUM(s.pediatria) AS Pediatria,
            SUM(s.gineco)    AS Ginecobstetricia,
            SUM(s.otros)     AS Otros
        FROM sinerhias s
    """

    if filtros:
        query += " WHERE " + " AND ".join(filtros)

    query += " GROUP BY s.anio, s.clues"

    cursor.execute(query, valores)
    data = cursor.fetchall()
    cursor.close()

    return jsonify(data)

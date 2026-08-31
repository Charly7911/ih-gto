from flask import Blueprint, render_template
from flask_login import login_required
from flask_mysqldb import MySQLdb
from app import mysql

# Blueprint para SIS Primer Nivel
sis_pn = Blueprint('sis_pn', __name__, url_prefix='/sis-primer-nivel')


@sis_pn.route("/")
@login_required
def dashboard_sis_primer_nivel():
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    # Consulta adaptada para primer nivel (Asegúrate de cambiar la tabla si se llama diferente)
    query = """
        SELECT 
            anio,
            mes,
            clues,
            nombre_unidad,
            consultas,
            mental,
            bucal,
            embarazadas,
            planificacion_familiar,
            detecciones,
            tamiz
            
        FROM sis_primer_nivel_registros
        ORDER BY anio, mes, clues
    """

    cursor.execute(query)
    resultados = cursor.fetchall()

    # Filtros dinámicos basados en la consulta
    anios_disponibles = sorted({r["anio"] for r in resultados}) if resultados else []
    unidades_disponibles = sorted({r["nombre_unidad"] for r in resultados}) if resultados else []

    # Consulta de control de estatus
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
        control_anual=control_anual,
        title="Reporte SIS - Primer Nivel"
    )
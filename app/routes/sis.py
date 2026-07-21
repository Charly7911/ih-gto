from flask import Blueprint, render_template
from flask_mysqldb import MySQLdb
from flask_login import login_required
from app import mysql

sis = Blueprint('sis', __name__, url_prefix='/sis')


@sis.route("/")
@login_required
def dashboard_sis():
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    query = """
        SELECT 
            anio,
            mes,
            clues,
            nombre_unidad,
            consultas,
            especialidad,
            mental,
            bucal,
            diasPaciente,
            no_medicas,
            med_interna,
            cirugia,
            gineco,
            pediatria,
            otros,
            psiquiatria,
            laboratorio,
            rayosx,
            anatomia,
            electro,
            encefa,
            ultrasonido,
            tac,
            rnm,
            medicas
        FROM sis_registros_agregados
        ORDER BY anio, mes, clues
    """

    cursor.execute(query)
    resultados = cursor.fetchall()

    # filtros disponibles
    anios_disponibles = sorted({r["anio"] for r in resultados})
    unidades_disponibles = sorted({r["nombre_unidad"] for r in resultados})


    cursor.execute("""
        SELECT anio, estatus_inicio, fecha_actualizacion, estatus
        FROM sis_control_anual
        ORDER BY anio
    """)
    control_anual = cursor.fetchall()



    cursor.close()

    return render_template(
        "sis/reporte_sis.html",
        resultados=resultados,
        anios_disponibles=anios_disponibles,
        unidades_disponibles=unidades_disponibles,
        control_anual=control_anual,
        title="Reporte SIS"
    )

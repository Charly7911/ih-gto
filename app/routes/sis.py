from flask import Blueprint, jsonify, render_template, request
from flask_mysqldb import MySQLdb
from flask_login import login_required
from app import mysql

sis = Blueprint('sis', __name__, url_prefix='/sis')

'''

# Consultas
consultas_vars = [
    "CON01","CON02","CON03","CON04","CON05","CON06","CON07","CON08","CON09","CON10",
    "CON11","CON12","CON13","CON14","CON15","CON16","CON17","CON18","CON19","CON20",
     "CON21","CON22","CON23","CON24","CON25","CON26","CON27","CON28","CON29","CON30",
    "CON31","CON32","CON33","CON34","CON35","CON36","CON37","CON38","CON39","CON40",
     "CON41","CON42","CON43","CON44","CON45","CON46","CON47",
     "COD01","COD02"
]

# Especialidad
especialidad_vars = [
    "CES01","CES02","CES03","CES04","CES05","CES06","CES07",
    "CES08","CES09","CES10","CES11","CES12","CES13","CES14",
    "CES15","CES16","CES17","CES18",
    "HPC03", "HPC04", "HPC05", "HPC08",
    "HPC10", "HPC11", "HPC12", "HPC15", "HPC17",
    "HPC18", "HPC19", "HPC22", "HPC24", "HPC25",
    "HPC26", "HPC29"
]

# Mental
mental_vars = ["CPP07", "CPP14", "HPC06", "HPC13", "HPC20", "HPC27"]

# Bucal
bucal_vars = ["CPP06", "CPP13", "HPC09", "HPC16", "HPC23", "HPC30", "COD01", "COD02"]

# No medicas
no_medicas_vars = [
    "CNM01","CNM02","CNM03","CNM04","CNM05","CNM06","CNM07","CNM08","CNM09","CNM10",
    "CNM11","CNM12","CNM13","CNM14","CNM15","CNM16","CNM17","CNM18","CNM19","CNM20",
    "CNM21","CNM22","CNM23","CNM24","CNM25","CNM26","CNM27","CNM28","CNM29","CNM30",
     "CNM31","CNM32","CNM33","CNM34","CNM35","CNM36","CNM37"
    ]

#ESTUDIOS
laboratorio_vars = ["LAB01"]
rayosX_vars = ["LRX01"]
anatomia_vars = ["LAP01"]
electrocardiograma_vars = ["LOE01"]
encefalograma_vars = ["LEN01","HPE10"]
ultrasonidos_vars = ["LUS01"]
tac_vars = ["LTC01"]
rmn_vars = ["RSM01"]

#DIAS ESTANCIA
dias_paciente_vars = ["HOS01","HOS02","HOS03","HOS04","HOS05","HPH12"]
med_interna_vars = ["HOS02"]
cirugia_vars = ["HOS01"]
gineco_vars = ["HOS04"]
pediatria_vars = ["HOS03"]
otros_vars = ["HOS05"]
psiquiatria_vars = ["HPH12"]

@sis.route("/")
def dashboard_sis():
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    # Creamos las listas en formato SQL
    consultas_str = ",".join(f"'{v}'" for v in consultas_vars)
    especialidad_str = ",".join(f"'{v}'" for v in especialidad_vars)
    mental_str = ",".join(f"'{v}'" for v in mental_vars)
    bucal_str = ",".join(f"'{v}'" for v in bucal_vars)
    no_medicas_str =  ",".join(f"'{v}'" for v in no_medicas_vars)
    med_interna_str =  ",".join(f"'{v}'" for v in med_interna_vars)
    cirugia_str = ",".join(f"'{v}'" for v in cirugia_vars)
    gineco_str = ",".join(f"'{v}'" for v in gineco_vars)
    pediatria_str = ",".join(f"'{v}'" for v in pediatria_vars)
    otros_str = ",".join(f"'{v}'" for v in otros_vars)
    psiquiatria_str = ",".join(f"'{v}'" for v in psiquiatria_vars)
    dias_paciente_str =  ",".join(f"'{v}'" for v in dias_paciente_vars)
    laboratorio_str =  ",".join(f"'{v}'" for v in laboratorio_vars)
    rayosX_str =  ",".join(f"'{v}'" for v in rayosX_vars)
    anatomia_str =  ",".join(f"'{v}'" for v in anatomia_vars)
    electrocardiograma_str =  ",".join(f"'{v}'" for v in electrocardiograma_vars)
    encefalograma_str =  ",".join(f"'{v}'" for v in encefalograma_vars)
    ultrasonidos_str =  ",".join(f"'{v}'" for v in ultrasonidos_vars)
    tac_str =  ",".join(f"'{v}'" for v in tac_vars)
    rmn_str =  ",".join(f"'{v}'" for v in rmn_vars)
    

    query = f"""
        SELECT 
            sr.anio,
            sr.mes,
            sr.clues,
            cu.nombre_unidad,
            SUM(CASE WHEN sr.variable IN ({consultas_str}) THEN sr.total ELSE 0 END) AS consultas,
            SUM(CASE WHEN sr.variable IN ({especialidad_str}) THEN sr.total ELSE 0 END) AS especialidad,
            SUM(CASE WHEN sr.variable IN ({mental_str}) THEN sr.total ELSE 0 END) AS mental,
            SUM(CASE WHEN sr.variable IN ({bucal_str}) THEN sr.total ELSE 0 END) AS bucal,
            SUM(CASE WHEN sr.variable IN ({dias_paciente_str}) THEN sr.total ELSE 0 END) AS diasPaciente,
            SUM(CASE WHEN sr.variable IN ({no_medicas_str}) THEN sr.total ELSE 0 END) AS no_medicas,
            SUM(CASE WHEN sr.variable IN ({med_interna_str}) THEN sr.total ELSE 0 END) AS med_interna,
            SUM(CASE WHEN sr.variable IN ({cirugia_str}) THEN sr.total ELSE 0 END) AS cirugia,
            SUM(CASE WHEN sr.variable IN ({gineco_str}) THEN sr.total ELSE 0 END) AS gineco,
            SUM(CASE WHEN sr.variable IN ({pediatria_str}) THEN sr.total ELSE 0 END) AS pediatria,
            SUM(CASE WHEN sr.variable IN ({otros_str}) THEN sr.total ELSE 0 END) AS otros,
            SUM(CASE WHEN sr.variable IN ({psiquiatria_str}) THEN sr.total ELSE 0 END) AS psiquiatria,
            SUM(CASE WHEN sr.variable IN ({laboratorio_str}) THEN sr.total ELSE 0 END) AS laboratorio,
            SUM(CASE WHEN sr.variable IN ({rayosX_str}) THEN sr.total ELSE 0 END) AS rayosx,
            SUM(CASE WHEN sr.variable IN ({anatomia_str}) THEN sr.total ELSE 0 END) AS anatomia,
            SUM(CASE WHEN sr.variable IN ({electrocardiograma_str}) THEN sr.total ELSE 0 END) AS electro,
            SUM(CASE WHEN sr.variable IN ({encefalograma_str}) THEN sr.total ELSE 0 END) AS encefa,
            SUM(CASE WHEN sr.variable IN ({ultrasonidos_str}) THEN sr.total ELSE 0 END) AS ultrasonido,
            SUM(CASE WHEN sr.variable IN ({tac_str}) THEN sr.total ELSE 0 END) AS tac,
            SUM(CASE WHEN sr.variable IN ({rmn_str}) THEN sr.total ELSE 0 END) AS rnm,

             (
            SUM(CASE WHEN sr.variable IN ({consultas_str}) THEN sr.total ELSE 0 END)
        - (
                SUM(CASE WHEN sr.variable IN ({especialidad_str}) THEN sr.total ELSE 0 END)
            + SUM(CASE WHEN sr.variable IN ({mental_str}) THEN sr.total ELSE 0 END)
            + SUM(CASE WHEN sr.variable IN ({bucal_str}) THEN sr.total ELSE 0 END)
            + SUM(CASE WHEN sr.variable IN ({no_medicas_str}) THEN sr.total ELSE 0 END)
            )
        ) AS medicas
        FROM sis_registros sr
        LEFT JOIN catalogo_unidades cu ON sr.clues = cu.clues
        GROUP BY sr.anio, sr.mes, sr.clues, cu.nombre_unidad
        ORDER BY sr.anio, sr.mes, sr.clues
    """

    cursor.execute(query)
    resultados = cursor.fetchall()

    # filtros disponibles
    anios_disponibles = sorted({r["anio"] for r in resultados})
    unidades_disponibles = sorted({r["nombre_unidad"] for r in resultados})


    cursor.close()

    return render_template(
        "sis/reporte_sis.html",
        resultados=resultados,
        anios_disponibles=anios_disponibles,
        unidades_disponibles=unidades_disponibles,
        title="Reporte SIS"
    )

    '''

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

import MySQLdb
from flask import Blueprint, request, jsonify, render_template
from flask_login import login_required
from app.controllers.egresos_controller import obtener_indicador
from app import mysql


indicador = Blueprint('indicador', __name__, url_prefix='/indicadores')

@indicador.route("/")
def dashboard_indicadores():
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
    return render_template("indicadores/indicador.html",  
        anios_disponibles=anios,
        unidades_disponibles=unidades,
        control_anual=control_anual,
        title="Reporte Indicadores")


@indicador.route('/api/tabla_base')
def api_tabla_base():
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    anios = [a for a in request.args.get('anios', '').split(',') if a]
    meses = [m for m in request.args.get('meses', '').split(',') if m]
    unidades = [u for u in request.args.get('unidades', '').split(',') if u]

    # ... (Toda tu lógica de filtros y construcción de query se queda igual) ...
    # Filtros base
    filtros_comun, valores_comun = [], []
    if anios:
        filtros_comun.append(f"anio IN ({','.join(['%s']*len(anios))})"); valores_comun.extend(anios)
    if meses:
        filtros_comun.append(f"mes IN ({','.join(['%s']*len(meses))})"); valores_comun.extend(meses)

    filtros_e = list(filtros_comun)
    valores_e = list(valores_comun)
    if unidades:
        filtros_e.append(f"nombre_unidad IN ({','.join(['%s']*len(unidades))})"); valores_e.extend(unidades)

    filtros_urg, valores_urg = [], []
    if anios:
        filtros_urg.append(f"anio IN ({','.join(['%s']*len(anios))})"); valores_urg.extend(anios)
    if meses:
        filtros_urg.append(f"mes_estadistico IN ({','.join(['%s']*len(meses))})"); valores_urg.extend(meses)

    where_e = "WHERE " + " AND ".join(filtros_e) if filtros_e else ""
    where_mov = "WHERE " + " AND ".join(filtros_comun) if filtros_comun else ""
    where_urg = "WHERE " + " AND ".join(filtros_urg) if filtros_urg else ""

    valores_totales = valores_e + valores_comun + valores_comun + valores_urg

    query = f"""
        SELECT
            e.anio, e.mes, e.clues, e.nombre_unidad,
            SUM(e.dias_estancia_med_interna) AS dias_estancia_med_interna,
            SUM(e.dias_estancia_cirugia) AS dias_estancia_cirugia,
            SUM(e.dias_estancia_pediatria) AS dias_estancia_pediatria,
            SUM(e.dias_estancia_ginecobstetricia) AS dias_estancia_gineco,
            SUM(e.dias_estancia_otros) AS dias_estancia_otros,
            AVG(e.prom_estancia_med_interna) AS prom_estancia_med_interna,
            AVG(e.prom_estancia_cirugia) AS prom_estancia_cirugia,
            AVG(e.prom_estancia_pediatria) AS prom_estancia_pediatria,
            AVG(e.prom_estancia_ginecobstetricia) AS prom_estancia_gineco,
            AVG(e.prom_estancia_otros) AS prom_estancia_otros,
            SUM(e.total_egresos) AS total_egresos,
            SUM(e.egresos_48h) AS egresos_48h,
            SUM(e.defunciones) AS total_defunciones,
            SUM(e.defunciones_48h) AS defunciones_48h,
            SUM(e.dias_estancia_sum) AS total_dias_estancia,
            SUM(e.nacimientos) AS total_nacimientos,
            SUM(e.cesareas) AS total_cesareas,
            SUM(e.abortos) AS total_abortos,
            SUM(e.apeo) AS total_apeo,
            IFNULL(SUM(p.total_cirugias), 0) AS total_cirugias_quirofano,
            IFNULL(SUM(sis.total_dias_paciente), 0) AS total_dias_paciente,
            IFNULL(SUM(sis.consultas), 0) AS total_consultas,
            IFNULL(SUM(sis.especialidad), 0) AS total_especialidad,
            IFNULL(SUM(urg.total_urgencias), 0) AS total_urgencias,
            IFNULL(SUM(urg.urgencias_calificadas), 0) AS total_urgencias_calificadas,
            MAX(sin.camas_total) AS camas_censables,
            MAX(sin.quirofanos) AS quirofanos,
            MAX(sin.camas_med_int) AS camas_med_int,
            MAX(sin.camas_cirugia) AS camas_cirugia,
            MAX(sin.camas_gineco) AS camas_gineco,
            MAX(sin.camas_pediatria) AS camas_pediatria,
            MAX(sin.camas_otros) AS camas_otros,
            MAX(sin.salas_expulsion) AS salas_expulsion,
            MAX(sin.quirofanos) AS quirofanos
            
        FROM (
            SELECT
                anio,
                mes,
                clues,
                nombre_unidad,

                total_egresos,
                egresos_48h,

                defunciones,
                defunciones_48h,

                dias_estancia_sum,

                dias_estancia_med_interna,
                dias_estancia_cirugia,
                dias_estancia_pediatria,
                dias_estancia_ginecobstetricia,
                dias_estancia_otros,

                prom_estancia_med_interna,
                prom_estancia_cirugia,
                prom_estancia_pediatria,
                prom_estancia_ginecobstetricia,
                prom_estancia_otros,

                nacimientos,
                cesareas,
                abortos,
                apeo

            FROM egresos_agregado
            {where_e}
        ) e
        LEFT JOIN (
            SELECT anio, mes, clues, SUM(total_proced_dentro) AS total_cirugias 
            FROM procedimiento_agregado {where_mov} GROUP BY anio, mes, clues
        ) p ON e.clues = p.clues AND e.anio = p.anio AND e.mes = p.mes
        LEFT JOIN (
            SELECT anio, mes, clues, SUM(diasPaciente) AS total_dias_paciente, 
                   SUM(consultas) AS consultas, SUM(especialidad) AS especialidad
            FROM sis_registros_agregados {where_mov} GROUP BY anio, mes, clues
        ) sis ON e.clues = sis.clues AND e.anio = sis.anio AND e.mes = sis.mes
        LEFT JOIN (
            SELECT anio, mes_estadistico, clues, SUM(total) AS total_urgencias, 
                   SUM(calificada) AS urgencias_calificadas
            FROM urgencias_agregado {where_urg} GROUP BY anio, mes_estadistico, clues
        ) urg ON e.clues = urg.clues AND e.anio = urg.anio AND e.mes = urg.mes_estadistico
       LEFT JOIN (
            SELECT
                anio,
                clues,

                MAX(total) AS camas_total,
                MAX(med_int) AS camas_med_int,
                MAX(cirugia) AS camas_cirugia,
                MAX(gineco) AS camas_gineco,
                MAX(pediatria) AS camas_pediatria,
                MAX(otros) AS camas_otros,
                MAX(quirofanos) AS quirofanos,
                MAX(salas_expulsion) AS salas_expulsion

            FROM sinerhias
            GROUP BY anio, clues
        ) sin
        ON e.clues = sin.clues
        AND e.anio = sin.anio
        GROUP BY e.anio, e.mes, e.clues, e.nombre_unidad
    """
    
    cursor.execute(query, valores_totales)
    rows = cursor.fetchall()
    cursor.close()

    # --- PROCESAMIENTO DE INDICADORES ---
    # Calculamos los porcentajes fila por fila (mes por mes)
    for row in rows:
        # 1. Porcentaje APEO: Total de Eventos Obstétricos (Nacimientos + Abortos)
        eventos_obstetricos = float(row['total_nacimientos'] or 0) + float(row['total_abortos'] or 0)
        row['porcentaje_apeo'] = (float(row['total_apeo'] or 0) / eventos_obstetricos * 100) if eventos_obstetricos > 0 else 0
        
        # 2. Promedio Días Estancia
        row['prom_dias_estancia'] = (float(row['total_dias_estancia'] or 0) / float(row['total_egresos'] or 1)) if row['total_egresos'] > 0 else 0
        
        # 3. Índice de Rotación (Egresos / Camas)
        row['indice_rotacion'] = (float(row['total_egresos'] or 0) / float(row['camas_censables'] or 1)) if row['camas_censables'] > 0 else 0

        # 4. Porcentaje de Urgencias Calificadas
        row['porcentaje_urg_calificada'] = (float(row['total_urgencias_calificadas'] or 0) / float(row['total_urgencias'] or 1) * 100) if row['total_urgencias'] > 0 else 0

           

    return jsonify(rows)

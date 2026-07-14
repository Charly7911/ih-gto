# utils/egresos_queries.py
import MySQLdb

def _csv_to_list(param):
    if isinstance(param, list):
        return param
    return [p.strip() for p in param.split(',') if p.strip()]


def construir_query(indicador, meses, anio, tipologias, unidades, modo="tabla"):
    meses_list = _csv_to_list(meses)
    params = []

    # 0) Estas columnas son invisibles en la tabla, pero necesarias para las tarjetas KPI
    columnas_kpi = """,
      SUM(COALESCE(e.total_egresos, 0)) AS KPI_Egresos_Totales,
        SUM(COALESCE(e.defunciones, 0)) AS KPI_Defunciones_Totales,
        SUM(COALESCE(e.egresos_48h, 0)) AS KPI_Egresos_48h,
        SUM(COALESCE(e.defunciones_48h, 0)) AS KPI_Defunciones_48h
    """

    # Bloque para indicadores basados en la tabla 'egresos_agregado'
    if indicador in ["egresos", "defunciones", "defunciones48", "nacimientos"]:
        sql = """
            SELECT 
                e.clues AS CLUES, 
                COALESCE(c.nombre_unidad, '') AS Hospital, 
                e.anio AS anio
        """
        if modo == "grafica":
            sql += ", e.mes AS mes "
        
        # SIEMPRE agregamos las columnas KPI
        sql += columnas_kpi

        if indicador == "egresos":
            sql += """,
                SUM(e.med_interna) AS Med_Interna, SUM(e.cirugia) AS Cirugía,
                SUM(e.ginecobstetricia) AS  Ginecobstetricia, SUM(e.pediatria) AS Pediatría,
                SUM(e.otros) AS Otros,
                SUM(e.med_interna + e.cirugia + e.ginecobstetricia + e.pediatria + e.otros) AS Total
            """
        elif indicador == "defunciones":
            sql += """,
                SUM(e.defunciones_med_interna) AS Med_Interna, SUM(e.defunciones_cirugia) AS Cirugía,
                SUM(e.defunciones_ginecobstetricia) AS Ginecobstetricia, SUM(e.defunciones_pediatria) AS Pediatría,
                SUM(e.defunciones_otros) AS Otros,
                (SUM(e.defunciones_med_interna) + SUM(e.defunciones_cirugia) + SUM(e.defunciones_ginecobstetricia) + SUM(e.defunciones_pediatria) + SUM(e.defunciones_otros)) AS Total
            """
        elif indicador == "defunciones48":
            sql += """,
                SUM(e.def_48h_med_interna) AS Med_Interna, SUM(e.def_48h_cirugia) AS Cirugía,
                SUM(e.def_48h_ginecobstetricia) AS Ginecobstetricia, SUM(e.def_48h_pediatria) AS Pediatría,
                SUM(e.def_48h_otros) AS Otros,
                (SUM(e.def_48h_med_interna) + SUM(e.def_48h_cirugia) + SUM(e.def_48h_ginecobstetricia) + SUM(e.def_48h_pediatria) + SUM(e.def_48h_otros)) AS Total
            """
        elif indicador == "nacimientos":
            sql += """,
                SUM(e.nac_eutocico) AS Eutócico, SUM(e.nac_distocico) AS Distócico, SUM(e.nac_cesarea) AS Cesárea,
                SUM(e.nac_eutocico + e.nac_distocico + e.nac_cesarea) AS Total
            """
        
        sql += " FROM egresos_agregado e LEFT JOIN catalogo_unidades c ON e.clues = c.clues "


    # Bloque para Procedimientos con KPIs Blindados (Evita duplicados)
    elif indicador in ["proc_dentro", "proc_fuera"]:
        sufijo = "dentro" if indicador == "proc_dentro" else "fuera"
        
        # 1. Filtros para los KPIs (Deben incluir la UNIDAD si se selecciona)
        where_kpi = []
        params_kpi = []
        
        if anio:
            anios_list = [int(a) for a in (anio if isinstance(anio, list) else anio.split(",")) if str(a).strip()]
            where_kpi.append(f"anio IN ({','.join(['%s']*len(anios_list))})")
            params_kpi.extend(anios_list)
            
        if meses_list:
            where_kpi.append(f"mes IN ({','.join(['%s']*len(meses_list))})")
            params_kpi.extend([int(m) for m in meses_list])
            
        # ¡ESTA ES LA CLAVE! Si hay unidades, los KPIs deben filtrarse por ellas
        if unidades:
            where_kpi.append(f"clues IN (SELECT clues FROM catalogo_unidades WHERE nombre_unidad IN ({','.join(['%s']*len(unidades))}))")
            params_kpi.extend(unidades)
        
        filtro_kpi_str = (" WHERE " + " AND ".join(where_kpi)) if where_kpi else ""

        # 2. SQL Principal
        # Multiplicamos params_kpi * 4 porque el filtro se repite en las 4 subconsultas
        sql = f"""
            SELECT 
                p.clues AS CLUES, 
                c.nombre_unidad AS Hospital, 
                p.anio,
                (SELECT SUM(total_egresos) FROM egresos_agregado {filtro_kpi_str}) AS KPI_Egresos_Totales,
                (SELECT SUM(defunciones) FROM egresos_agregado {filtro_kpi_str}) AS KPI_Defunciones_Totales,
                (SELECT SUM(egresos_48h) FROM egresos_agregado {filtro_kpi_str}) AS KPI_Egresos_48h,
                (SELECT SUM(defunciones_48h) FROM egresos_agregado {filtro_kpi_str}) AS KPI_Defunciones_48h
        """
        
        if modo == "grafica": 
            sql += ", p.mes AS mes "
            
        sql += f""",
                SUM(p.med_int_proced_{sufijo}) AS Med_Interna, 
                SUM(p.cirugia_proced_{sufijo}) AS Cirugía,
                SUM(p.gineco_proced_{sufijo}) AS Ginecobstetricia, 
                SUM(p.pediatra_proced_{sufijo}) AS Pediatría,
                SUM(p.otros_proced_{sufijo}) AS Otros, 
                SUM(p.total_proced_{sufijo}) AS Total
            FROM procedimiento_agregado p
            LEFT JOIN catalogo_unidades c ON p.clues = c.clues
        """
        
        # Guardamos los parámetros de los KPIs para el inicio de la consulta
        params = params_kpi * 4

    # --- Lógica común de Filtros WHERE ---
    where = []
    if anio:
        anios_list = [int(a) for a in (anio if isinstance(anio, list) else anio.split(",")) if str(a).strip()]
        if anios_list:
            where.append(f"{'e' if indicador != 'proc_dentro' and indicador != 'proc_fuera' else 'p'}.anio IN ({','.join(['%s']*len(anios_list))})")
            params.extend(anios_list)
    
    if meses_list:
        where.append(f"{'e' if indicador != 'proc_dentro' and indicador != 'proc_fuera' else 'p'}.mes IN ({','.join(['%s']*len(meses_list))})")
        params.extend([int(m) for m in meses_list])

    if unidades:
        where.append(f"c.nombre_unidad IN ({','.join(['%s']*len(unidades))})")
        params.extend(unidades)

    if where:
        sql += " WHERE " + " AND ".join(where)

    # --- Group By y Order By ---
    alias = 'e' if indicador not in ["proc_dentro", "proc_fuera"] else 'p'
    sql += f" GROUP BY {alias}.clues, c.nombre_unidad, {alias}.anio"
    if modo == "grafica":
        sql += f", {alias}.mes ORDER BY c.nombre_unidad, {alias}.anio, {alias}.mes"
    else:
        sql += f" ORDER BY c.nombre_unidad, {alias}.anio"

    return sql, tuple(params)
    
   



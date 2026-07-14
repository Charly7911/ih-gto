# controllers/egresos_controller.py
import MySQLdb
from app import mysql
from app.utils.egresos_queries import construir_query

def obtener_indicador(nombre, meses, tipologias, anio, unidades=None, modo="tabla"):
    """
    Llama al builder de query y ejecuta la consulta contra MySQL,
    devolviendo una lista de diccionarios (filas).
    """

    sql, params = construir_query(
        indicador=nombre,
        meses=meses,
        anio=anio,
        tipologias=tipologias,
        unidades=unidades,
        
        modo=modo
    )

    

    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close()

    return rows


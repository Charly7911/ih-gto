from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required
from flask_mysqldb import MySQLdb
from app import mysql, csrf

sis_pn = Blueprint('sis_pn', __name__, url_prefix='/sis_primer_nivel')

VARIABLES_DEFAULT = {
    "consultas": [
        'CON01','CON02','CON03','CON04','CON05','CON06','CON07','CON08','CON09','CON10',
        'CON11','CON12','CON13','CON14','CON15','CON16','CON17','CON18','CON19','CON20',
        'CON21','CON22','CON23','CON24','CON25','CON26','CON27','CON28','CON29','CON30',
        'CON31','CON32','CON33','CON34','CON35','CON36','CON37','CON38','CON39','CON40',
        'CON41','CON42','CON44','CON45','CON47','COD01','COD02'
    ],
    "mental": ['CPP07', 'CPP14'],
    "bucal": ['CPP06', 'CPP13', 'COD01', 'COD02'],
    "embarazadas": ['EMB01', 'EMB02', 'EMB03', 'EMB04', 'EMB05', 'EMB06'],
    "planificacion_familiar": [
        'PFC01','PFC02','PFC03','PFC04','PFC05','PFC06','PFC07','PFC08','PFC10',
        'PFC11','PFC12','PFC13','PFC14','PFC15','PFC16','PFC17','PFC19','PFC20',
        'PFC21','PFC22','PFC23','PFC24','PFC25','PFC26','PFC27','PFC28','PFC29',
        'PFC30','PFC31','PFC32'
    ],
    "detecciones": [
        'DET01','DET02','DET03','DET04','DET05','DET06','DET07','DET08','DET09',
        'DET11','DET12','DET16','DET17','DET18','DET19','DET21','DET22','DET25',
        'DET26','DET27','DET28','DET29','DET30','DET31','DET33','DET34','DET35',
        'DET36','DET39','DET40','DET42','DET43','DET44','DET45','DET47','DET50',
        'DET51','DET52','DET53','DET54','DET57','DET58','DET59','DET60','DET61',
        'DET62','DET63','DET64','DET73','DET74','DET85','DET86','DET87','DET88',
        'DET89','DET90','DET91','DET92','DET93','DET94','DET95','DET96','DET97',
        'DET98','DET99','DT001','DT002','DT003','DT004','DT005','DT006','DT007',
        'DT008','DT009','DT010','DT011','DT012','DT013','DT014','DT015','DT016',
        'DT017','DT018','DT019','DT020','DT021','DT022','DT023','DT024','DT025',
        'DT026','DT027','DT028','DT030','DT031','DT032','DT033','DT034','DT035',
        'DT036','DT037','DT038','DT039','DT040','DT041','DT042','DT043','DT044',
        'DT045','DT046','DT047','DT048','DT049','DT050','DT051','DT053','DT054',
        'DT055','DT056','DT059','DT060','DT061','DT062','DT063','DT064','DT065',
        'DT066','DT067','DT068','DT069','DT070','DT071','DT072','DT073','DT074',
        'DT075','DT076','DT077','DT078','DT079','DT080','DT081','DT082','DT083',
        'DT084','DT085','DT086','DT087','DT088','DT089','DT090','DT091','DT092',
        'DT093','DT094','DT095','DT096','DT097','DT098','DT099','DT100','DT101',
        'DT102','DT103','DT104','DT105','DT106','DT107','DT108','DT109','DT110',
        'DT111','DT112','DT113','DT114','DT115','DT116','DT117','DT118','DT119',
        'DT120','DT121','DT122','DT123','DT124','DT125','DT126','DT127','DT128',
        'DT129','DT130','DT131','DT132','DT133','DT134','DT135','DT136','DT137',
        'DT138','DT139','DT140','DT141','DT142','DT143','DT144','DT145','DT146',
        'DT147','DT148','DT149','DT150','DT151','DT152','DT153','DT154','DT155',
        'DT156','DT157','DT158','DT159','DT160','DT161','DT162','DT163','DT165',
        'DT166','DT167','DT168','DT169','DT170','DT171','DT172','DT173','DT174',
        'DT175','DT176','DT177','DT178','DTE01','DTE02','DTE03','DTE04','DTE05',
        'DTE06','DTE07','DTE08','DTE09','DTE10','DTE11','DTE12','DTE14','DTE15',
        'DTE16','DTE17','DTE18','DTE19','DTE20','DTE21','DTE22','DTE23','DTE24',
        'DTE25','DTE32','DTE33','DTE37','DTE38','DTE40','DTE41','DTE42','DTE43',
        'DTE44','DTE45','DTE46','DTE47','DTE48','DTE49','DTE56','DTE57','DTE61',
        'DTE62','DTE64','DTE65','DTE66','DTE67','DTE68','DTE69','DTE70','DTE71',
        'DTE72','DTE73','DTE74','DTE75','DTE76','DTE77','DTE78','DTE79','DTE80',
        'DTE81','DTE82','DTE83','DTE84','DTE85','DTE86','DTE87','DTE88','DTE89',
        'DTE90','DTE91','DTE92','DTE93','DTE94','DTE95','DTE96','DTE97','DTE98','DTE99'
    ],
    "detecciones_cardiometabolicas": ['DET01','DET02','DET03','DET04','DET25','DET26','DET27','DET28','DET50','DET51','DET52','DET53','DET58','DET59','DET60','DET61'],
    "tamiz": ['RNL06'],
    "orientacion_lac_des_obe": ['MAC07', 'MAC08', 'MAC09', 'MAC11', 'MAC12'],
    "orientacion_eda_ira": ['MAC01', 'MAC02']
}

def _construir_clausula_in(columna, lista):
    if not lista:
        return "", []
    placeholders = ','.join(['%s'] * len(lista))
    return f" AND {columna} IN ({placeholders})", list(lista)

def obtener_modulo_por_apartado(apartado_raw, variable_code=""):
    apt = str(apartado_raw or "").strip()
    var = str(variable_code or "").upper().strip()

    # Evaluaciones específicas por código de variable (mayor prioridad)
    if var in ['MAC07', 'MAC08', 'MAC09', 'MAC11', 'MAC12']:
        return "orientacion_lac_des_obe"
    elif var in ['MAC01', 'MAC02']:
        return "orientacion_eda_ira"
    elif var in ['DET01','DET02','DET03','DET04','DET25','DET26','DET27','DET28','DET50','DET51','DET52','DET53','DET58','DET59','DET60','DET61']:
        return "detecciones_cardiometabolicas"

    # Evaluaciones generales (menor prioridad)
    elif apt in ["1", "01", "215"] or var.startswith("CON"):
        return "consultas"
    elif apt in ["24"] or var.startswith("EMB"):
        return "embarazadas"
    elif apt in ["36"] or var.startswith(("PFC", "PLA")):
        return "planificacion_familiar"
    elif apt in ["56"] or var.startswith(("DET", "DT0", "DT1", "DTE")):
        return "detecciones"
    elif apt in ["111"] or var.startswith(("RNL", "TAM")):
        return "tamiz"
    elif apt in ["2", "02"] and var in ['CPP06', 'CPP13', 'COD01', 'COD02']:
        return "bucal"
    elif apt in ["2", "02"] and var in ['CPP07', 'CPP14']:
        return "mental"
    else:
        return "consultas"

@sis_pn.route("/")
@login_required
def dashboard_sis_primer_nivel():
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    try:
        # Cargar los registros agrupados de los últimos años (sin que LIMIT 2000 lo ahoque)
        query = """
            SELECT 
                anio, mes, clues, nombre_unidad, jurisdiccion, municipio,
                consultas, mental, bucal, embarazadas, planificacion_familiar, detecciones, tamiz,
                detecciones_cardiometabolicas, orientacion_lac_des_obe, orientacion_eda_ira
            FROM sis_registros_agregados_primer_nivel
            WHERE anio >= YEAR(CURDATE()) - 3  -- 👈 Carga los últimos 3 ó 4 años completos
            ORDER BY anio DESC, mes DESC, clues
        """
        cursor.execute(query)
        resultados = cursor.fetchall() or []

        # Asegurar que anio siempre sea int en Python antes de mandarlo a la plantilla
        for r in resultados:
            if r.get("anio") is not None:
                r["anio"] = int(r["anio"])

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

        cursor.execute("""
            SELECT anio, estatus_inicio, fecha_actualizacion, estatus
            FROM sis_control_anual_primer_nivel
            ORDER BY anio
        """)
        rows_control = cursor.fetchall() or []
        control_anual = [
            {**row, "fecha_actualizacion": str(row["fecha_actualizacion"]) if row.get("fecha_actualizacion") else None}
            for row in rows_control
        ]

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

            mod = obtener_modulo_por_apartado(apt, code)

            if apt in ["2", "02"] and mod == "consultas":
                continue

            catalogo_estructurado.setdefault(mod, {}).setdefault(apt, {
                "apartado": apt,
                "descripcion_apartado": desc_apt,
                "variables": []
            })["variables"].append({"codigo": code, "nombre": nombre_var})

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
        variables_default=VARIABLES_DEFAULT,
        tipo="sis",
        title="Reporte SIS - Primer Nivel"
    )

@sis_pn.route("/api/filtrar", methods=["POST"])
@login_required
@csrf.exempt
def filtrar_datos_sis():
    data = request.get_json(silent=True) or {}

    unidades = data.get("unidades", []) or []
    jurisdicciones = data.get("jurisdicciones", []) or []
    municipios = data.get("municipios", []) or []
    anios = [int(a) for a in data.get("anios", []) if str(a).isdigit()]
    meses = [int(m) for m in data.get("meses", []) if str(m).isdigit()]
    variables_seleccionadas = data.get("variables", {}) or {}

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    try:
        tiene_variables_custom = isinstance(variables_seleccionadas, dict) and any(
            isinstance(v, list) and len(v) > 0 for v in variables_seleccionadas.values()
        )

        if not tiene_variables_custom:
            query_base = """
                SELECT 
                    anio, mes, clues, nombre_unidad, jurisdiccion, municipio,
                    consultas, mental, bucal, embarazadas, planificacion_familiar, detecciones, tamiz, 
                    detecciones_cardiometabolicas, orientacion_lac_des_obe, orientacion_eda_ira 
                FROM sis_registros_agregados_primer_nivel
                WHERE 1=1
            """
            params = []

            if unidades:
                placeholders = ','.join(['%s'] * len(unidades))
                query_base += f" AND (clues IN ({placeholders}) OR nombre_unidad IN ({placeholders}))"
                params.extend(unidades + unidades)

            for col, lst in [('jurisdiccion', jurisdicciones), ('municipio', municipios), ('anio', anios), ('mes', meses)]:
                clausula, vals = _construir_clausula_in(col, lst)
                query_base += clausula
                params.extend(vals)

            query_base += " ORDER BY anio, mes, clues"
            cursor.execute(query_base, params)
            datos_filtrados = cursor.fetchall() or []

        else:
            def resolver_vars(mod_key):
                val = variables_seleccionadas.get(mod_key)
                if val is None:
                    return VARIABLES_DEFAULT[mod_key]
                return val if len(val) > 0 else ["__NONE__"]

            modulos = ["consultas", "mental", "bucal", "embarazadas", "planificacion_familiar", "detecciones", "tamiz", "detecciones_cardiometabolicas", "orientacion_lac_des_obe", "orientacion_eda_ira"]
            vars_map = {m: resolver_vars(m) for m in modulos}

            select_sums = []
            params = []
            for mod_key, v_list in vars_map.items():
                placeholders = ','.join(['%s'] * len(v_list))
                select_sums.append(
                    f"SUM(CASE WHEN sr.variable IN ({placeholders}) THEN CAST(sr.total AS UNSIGNED) ELSE 0 END) AS {mod_key}"
                )
                params.extend(v_list)

            query_base = f"""
                SELECT 
                    sr.anio, sr.mes, sr.clues, 
                    COALESCE(cu.nombre_unidad, sr.clues) AS nombre_unidad,
                    sr.jurisdiccion, sr.municipio,
                    {', '.join(select_sums)}
                FROM sis_registros_primer_nivel sr
                LEFT JOIN catalogo_unidades_primer_nivel cu ON sr.clues = cu.clues
                WHERE 1=1
            """

            if unidades:
                placeholders = ','.join(['%s'] * len(unidades))
                query_base += f" AND (sr.clues IN ({placeholders}) OR cu.nombre_unidad IN ({placeholders}))"
                params.extend(unidades + unidades)

            for col, lst in [('sr.jurisdiccion', jurisdicciones), ('sr.municipio', municipios), ('sr.anio', anios), ('sr.mes', meses)]:
                clausula, vals = _construir_clausula_in(col, lst)
                query_base += clausula
                params.extend(vals)

            query_base += """
                GROUP BY sr.anio, sr.mes, sr.clues, cu.nombre_unidad, sr.jurisdiccion, sr.municipio
                ORDER BY sr.anio, sr.mes, sr.clues
            """

            cursor.execute(query_base, params)
            datos_filtrados = cursor.fetchall() or []

        return jsonify({"status": "success", "data": datos_filtrados})

    except Exception as e:
        print(f"❌ Error en API /api/filtrar: {str(e)}") # Depuración en consola del servidor
        return jsonify({"status": "error", "message": f"Error al procesar la consulta: {str(e)}"}), 400

    finally:
        cursor.close()
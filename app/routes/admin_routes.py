from collections import defaultdict

from datetime import datetime
import sqlite3
import numpy as np
import pandas as pd
import zipfile
import os
import shutil
import zipfile
import MySQLdb
from flask import Blueprint, current_app, render_template, request, redirect, session, url_for, flash
from flask_login import login_required, current_user
from app import mysql
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename


admin = Blueprint('admin', __name__)

@admin.route('/')
@login_required
def dashboard():
    if current_user.rol_id != 6:
        flash("Acceso no autorizado.")
        return redirect(url_for('main.dashboard'))
    return render_template('admin/dashboard.html')


# ------------------------------
# USUARIOS
# ------------------------------


@admin.route('/usuarios/crear', methods=['GET', 'POST'])
@login_required
def crear_usuario():
    if current_user.rol_id != 6:
        flash('No tienes permisos para acceder a esta página.', 'danger')
        return redirect(url_for('admin.index'))
    
    if request.method == 'POST':
        # Recopilar datos del formulario
        nombre = request.form.get('nombre').strip()
        primer_apellido = request.form.get('primer_apellido').strip()
        segundo_apellido = request.form.get('segundo_apellido').strip()
        sexo = request.form.get('sexo')
        rfc = request.form.get('rfc')
        email = request.form.get('email')
        username = request.form.get('username').strip()
        password = request.form.get('password').strip()
        rol_id = request.form.get('rol_id')
             
        
        # Validaciones básicas
        if not (nombre and primer_apellido and email and username and password and rol_id):
            flash('Por favor, completa todos los campos obligatorios.', 'danger')
            return redirect(url_for('admin.crear_usuario'))
        

        # Validar unicidad de username y correo
        try:
            cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
            cursor.execute("SELECT * FROM user WHERE username = %s", (username,))
            if cursor.fetchone():
                flash('El nombre de usuario ya está en uso. Por favor, elige otro.', 'danger')
                return redirect(url_for('admin.crear_usuario'))
            
            
            # Hashear la contraseña
            hashed_password = generate_password_hash(password, method='pbkdf2:sha256', salt_length=8)
            
            # Insertar el nuevo usuario en la base de datos
            cursor.execute("""
                INSERT INTO user
                (nombre, primer_apellido, segundo_apellido, sexo, rfc, email, username, password, rol_id, nombre_oculto)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                nombre,
                primer_apellido,
                segundo_apellido,
                sexo,
                rfc,
                email,
                username,
                hashed_password,
                rol_id,
                password  # Activo por defecto
            ))
            
            
            mysql.connection.commit()
            flash('Usuario registrado exitosamente.', 'success')
            return redirect(url_for('admin.crear_usuario'))
        
        except Exception as e:
            mysql.connection.rollback()
            current_app.logger.error(f'Error al registrar usuario: {e}')
            flash(f'Error al registrar usuario: {e}', 'danger')
            return redirect(url_for('admin.crear_usuario'))
        finally:
            cursor.close()
    
    else:
               
        # Obtener la lista de usuarios para la tabla
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        try:
            cursor.execute("""
                SELECT u.* 
                     
                FROM user u
               
                ORDER BY u.id DESC
            """)
            usuarios = cursor.fetchall()
        except Exception as e:
            current_app.logger.error(f'Error al obtener lista de usuario: {e}')
            usuarios = []
        finally:
            cursor.close()
        
        # Obtener los roles (tipo_rol) disponibles (debes tener una tabla de roles o definirlos)
        # Por simplicidad, este ejemplo asume que tienes roles definidos numéricamente
        roles = [
            {'id': 1, 'nombre': 'Usuario'},
            {'id': 2, 'nombre': 'Secretaria'},
            {'id': 3, 'nombre': 'Jefe Departamento'},
            {'id': 4, 'nombre': 'Director'},
            {'id': 5, 'nombre': 'Director General'},
            {'id': 6, 'nombre': 'Administrador'}

            # Añade más roles según tu aplicación
        ]
        
        return render_template('admin/crear_usuario.html',  usuarios=usuarios, roles=roles)
    

#********************* ELIMINAR USUARIO ************************
@admin.route('/eliminar_usuario/<int:id>', methods=['POST'])
@login_required
def eliminar_usuario(id):
    try:
        # Verificar si el usuario está asignado en la tabla de asignaciones
        cursor = mysql.connection.cursor()
        
        cursor.execute("DELETE FROM user WHERE id = %s", (id,))
        mysql.connection.commit()
        flash('Usuario eliminado exitosamente.', 'success')
    
    except Exception as e:
        mysql.connection.rollback()
        current_app.logger.error(f'Error al eliminar usuario {id}: {e}')
        flash('Hubo un error al eliminar el usuario.', 'danger')
    finally:
        cursor.close()
    
    return redirect(url_for('admin.crear_usuario'))
    
ALLOWED_EXTENSIONS = {'zip'}

def archivo_permitido(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

#*****************************************************************************************
#************************* SUBIR CARPETA Y ARCHIVO DE URGENCIAS***************************
#*****************************************************************************************

@admin.route('/upload_zip_urgencias', methods=['GET', 'POST'])
@login_required
def subir_zip_urgencias():
    if request.method == 'POST':
        # 📌 1. Obtención de datos del formulario (Asegúrate de capturar todos los campos)
        anio = int(request.form.get("anio"))
        modo_carga = request.form.get("modo_carga")
        fecha_actualizacion = request.form.get("fecha_actualizacion")
        estatus = request.form.get("estatus")
        estatus_inicio = request.form.get("estatus_inicio")

        # 📁 2. Validar archivo
        if 'file' not in request.files:
            flash('No hay archivo en la solicitud', 'danger')
            return redirect(url_for('admin.subir_zip_urgencias'))

        file = request.files['file']
        if file.filename == '' or not (file and archivo_permitido(file.filename)):
            flash('Archivo no válido o no seleccionado', 'danger')
            return redirect(url_for('admin.subir_zip_urgencias'))

        # 📂 3. Preparar carpeta destino
        carpeta_nombre = f"urgencias_{anio}"
        carpeta_destino = os.path.join(current_app.root_path, 'uploads', carpeta_nombre)

        if modo_carga == 'actualizar' and os.path.exists(carpeta_destino):
            shutil.rmtree(carpeta_destino)
        os.makedirs(carpeta_destino, exist_ok=True)

        # 💾 4. Guardar y descomprimir
        filename = secure_filename(file.filename)
        zip_path = os.path.join(carpeta_destino, filename)
        file.save(zip_path)

        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(carpeta_destino)

        # 🗃️ 5. Conexión a Base de Datos
        conn = mysql.connection
        cursor = conn.cursor()

        try:
            cursor.execute("SET FOREIGN_KEY_CHECKS = 0")

            # 🧹 Limpieza preventiva (Si es actualizar)
            if modo_carga == 'actualizar':
                cursor.execute("DELETE FROM urgencias_registros WHERE anio = %s", (anio,))
                cursor.execute("DELETE FROM urgencias_agregado WHERE anio = %s", (anio,))
                conn.commit()

            # 6. Historial de carga
            cursor = conn.cursor()
            sql_historial = "INSERT INTO cargas_zip (nombre_zip, carpeta_destino, usuario_id) VALUES (%s, %s, %s)"
            valores_historial = (filename, carpeta_nombre, session['user_id'])
            cursor.execute(sql_historial, valores_historial)
            carga_id = cursor.lastrowid

            # 7. Procesar TXT y Recálculo
            procesar_txt_detallado_urgencias(carga_id, carpeta_destino, anio)
            conn.commit()

            actualizar_urgencias_agregado(anio)
            conn.commit()

            # 8. AQUÍ ESTÁ LO QUE FALTABA: Tabla de control anual
            # Esto inserta los datos que ves en el encabezado (span id="urgencias-meta")
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO urgencias_control_anual (anio, estatus_inicio, fecha_actualizacion, estatus)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    fecha_actualizacion = VALUES(fecha_actualizacion),
                    estatus_inicio = VALUES(estatus_inicio),
                    estatus = VALUES(estatus)
            """, (anio, estatus_inicio, fecha_actualizacion, estatus))

            # ✅ COMMIT FINAL
            conn.commit()
            flash(f'Datos de urgencias {anio} y control anual actualizados.', 'success')

        except Exception as e:
            conn.rollback()
            flash(f'Error: {str(e)}', 'danger')
            print(f"❌ Error: {e}")
        finally:
            cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
            cursor.close()

        return redirect(url_for('admin.subir_zip_urgencias'))

    return render_template('admin/subir_zip_urgencias.html')


def procesar_txt_detallado_urgencias(carga_id, carpeta_destino, anio_seleccionado):
    import pandas as pd
    import os
    
    conn = mysql.connection
    cursor = conn.cursor()

    # 🏥 1. Obtener el "Libro Blanco" de CLUES (Solo las que están en el catálogo)
    # Usamos un Set para que la validación sea instantánea
    cursor.execute("SELECT clues FROM catalogo_unidades")
    clues_validas = set(row[0].upper().strip() for row in cursor.fetchall())

    # 2. Obtener columnas de la DB para mapeo (excluyendo autoincrementales)
    cursor.execute("DESCRIBE urgencias_registros")
    columnas_db = [col[0] for col in cursor.fetchall() if 'auto_increment' not in col[5].lower() and col[0] != 'id']

    # 🔍 3. Localizar el archivo urgencias.txt
    path_urg = None
    for root, _, files in os.walk(carpeta_destino):
        for f in files:
            if f.lower().strip() == 'urgencias.txt':
                path_urg = os.path.join(root, f)
                break

    if not path_urg:
        print("❌ No se encontró el archivo urgencias.txt")
        return

    try:
        # 📖 4. Leer el archivo con Pandas
        df = pd.read_csv(path_urg, sep='|', encoding='utf-8-sig', dtype=str)
        
        # 🛡️ 5. APLICAR FILTRO ESTRICTO
        # Convertimos a mayúsculas y quitamos espacios para evitar errores de dedo
        if 'CLUES' in df.columns:
            df['CLUES'] = df['CLUES'].str.upper().str.strip()
            # Solo conservamos las filas cuya CLUE está en nuestro Set de permitidas
            df = df[df['CLUES'].isin(clues_validas)].copy()
            print(f"✅ Filtro aplicado: Se procesarán {len(df)} registros que coinciden con el catálogo.")
        else:
            print("⚠️ El archivo no contiene la columna 'CLUES'. Se aborta el filtrado.")
            return

        # 📅 6. Preparar columnas obligatorias
        df['anio'] = anio_seleccionado
        df['carga_id'] = carga_id

        # Asegurar que el DataFrame tenga todas las columnas que la DB pide
        for col in columnas_db:
            if col not in df.columns:
                df[col] = None
        
        # Reordenar columnas para que coincidan con la DB y limpiar NaNs
        df_final = df[columnas_db].copy()

        columnas_hora = ['HORASESTANCIA', 'hora_ingreso', 'hora_alta'] # Añade aquí otras si existen
        for col_h in columnas_hora:
            if col_h in df_final.columns:
                # Reemplaza 99:99, 9999 o cualquier cosa que no parezca hora por None
                df_final[col_h] = df_final[col_h].replace(['99:99', '9999', '99:9', ' : '], None)

        df_final = df_final.astype(object).replace({pd.NA: None, float('nan'): None, 'nan': None})
        df_final = df_final.where(pd.notnull(df_final), None)

        # 🚀 7. Inserción masiva por bloques (570k registros)
        bloque_size = 15000 # Aumentamos un poco el bloque para mayor velocidad
        valores = [tuple(x) for x in df_final.to_numpy()]
        total = len(valores)
        
        placeholders = ', '.join(['%s'] * len(columnas_db))
        columnas_sql = ', '.join(columnas_db)
        sql = f"INSERT INTO urgencias_registros ({columnas_sql}) VALUES ({placeholders})"

        for i in range(0, total, bloque_size):
            bloque = valores[i : i + bloque_size]
            cursor.executemany(sql, bloque)

            if i % 45000 == 0:
                conn.commit()
            print(f"⏳ Progreso: {i + len(bloque)} de {total} (Solo unidades autorizadas)")

        conn.commit()

    except Exception as e:
        print(f"❌ Error en el procesamiento: {e}")
        raise e
    finally:
        cursor.close()



def actualizar_urgencias_agregado(anio):
    cursor = mysql.connection.cursor()
    try:
        # Borrar solo el año a recalcular (evita duplicados)
        cursor.execute("DELETE FROM urgencias_agregado WHERE anio = %s", (anio,))

        sql = """
            INSERT INTO urgencias_agregado (
                clues, nombre_unidad, tipologia, mes_estadistico, anio,
                calificada, no_calificada, accidentes, medica, 
                ginecobstetricia, pediatrica, no_especificado, total
            )
            SELECT
                r.CLUES,
                MAX(cu.nombre_unidad),
                MAX(cu.tipologia),
                r.MES_ESTADISTICO,
                r.anio,
                SUM(CASE WHEN tu.Descrip LIKE '%%CALIFICADA%%' AND tu.Descrip NOT LIKE '%%NO%%' THEN 1 ELSE 0 END),
                SUM(CASE WHEN tu.Descrip LIKE '%%NO CALIFICADA%%' THEN 1 ELSE 0 END),
                SUM(CASE WHEN ma.Descrip LIKE '%%ACCIDENTES%%' THEN 1 ELSE 0 END),
                SUM(CASE WHEN ma.Descrip = 'MÉDICA' THEN 1 ELSE 0 END),
                SUM(CASE WHEN ma.Descrip LIKE '%%GINECO%%' THEN 1 ELSE 0 END),
                SUM(CASE WHEN ma.Descrip = 'PEDIÁTRICA' THEN 1 ELSE 0 END),
                SUM(CASE WHEN ma.Descrip = 'NO ESPECIFICADO' THEN 1 ELSE 0 END),
                COUNT(*)
            FROM urgencias_registros r
            LEFT JOIN catalogo_unidades cu ON cu.clues = r.CLUES
            LEFT JOIN catalogo_motivo_atencion ma ON r.MOTATE = ma.IDMotAte
            LEFT JOIN catalogo_tipourgencia tu ON r.TIPOURGENCIA = tu.IdTipoUrgencia
            WHERE r.anio = %s
            GROUP BY r.CLUES, r.MES_ESTADISTICO, r.anio
        """
        cursor.execute(sql, (anio,))
        print(f"📊 Indicadores de Urgencias {anio} actualizados.")
    finally:
        cursor.close()



#***************************************************************************************
#************************* SUBIR CARPETA Y ARCHIVO DE EGRESOS****************************
#****************************************************************************************

@admin.route('/upload_zip_egresos', methods=['GET', 'POST'])
@login_required
def subir_zip_egresos():
    if request.method == 'POST':
        

        anio = int(request.form.get("anio"))
        fecha_actualizacion = request.form.get("fecha_actualizacion")
        estatus = request.form.get("estatus")
        estatus_inicio = request.form.get("estatus_inicio")
        modo_carga = request.form.get("modo_carga")

        # 📁 2. Validar archivo
        if 'file' not in request.files:
            flash('No hay archivo en la solicitud', 'danger')
            return redirect(url_for('admin.subir_zip_egresos'))

        file = request.files['file']
        if file.filename == '' or not (file and archivo_permitido(file.filename)):
            flash('Archivo no válido o no seleccionado', 'danger')
            return redirect(url_for('admin.subir_zip_egresos'))

        # 📂 3. Preparar carpeta destino
        carpeta_nombre = f"egresos_{anio}"
        carpeta_destino = os.path.join(current_app.root_path, 'uploads', carpeta_nombre)

        if modo_carga == 'actualizar' and os.path.exists(carpeta_destino):
            shutil.rmtree(carpeta_destino)
        os.makedirs(carpeta_destino, exist_ok=True)

        # 💾 4. Guardar y descomprimir
        filename = secure_filename(file.filename)
        zip_path = os.path.join(carpeta_destino, filename)
        file.save(zip_path)

        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(carpeta_destino)

        # 🗃️ 5. Conexión a Base de Datos
        conn = mysql.connection
        cursor = conn.cursor()

        try:
            # 🔓 Desactivar checks para todo el proceso
            cursor.execute("SET FOREIGN_KEY_CHECKS = 0")

            # 🧹 SI ES REEMPLAZAR → Limpiar (SIN COMMIT AQUÍ)
            if modo_carga == "actualizar":
                cursor.execute("DELETE FROM egresos_registros WHERE anio = %s", (anio,))
                cursor.execute("DELETE FROM procedimientos_registros WHERE anio = %s", (anio,))
                cursor.execute("DELETE FROM egresos_agregado WHERE anio = %s", (anio,))
                cursor.execute("DELETE FROM procedimiento_agregado WHERE anio = %s", (anio,))
                print(f"🧹 Limpieza del año {anio} preparada.")

            # 🧾 6. Registrar historial
            cursor.execute("""
                INSERT INTO cargas_zip (nombre_zip, carpeta_destino, usuario_id)
                VALUES (%s, %s, %s)
            """, (filename, carpeta_nombre, session['user_id']))
            carga_id = cursor.lastrowid

            # ⚙️ 7. Procesar TXT (Quitamos el commit que tenías aquí)
            procesar_txt_detallado_egresos(carga_id, carpeta_destino, anio, modo_carga)

            # ⚙️ 8. Realizar cálculos (Quitamos los commits de estas funciones también)
            recalcular_procedimiento_agregado(anio)
            recalcular_egresos_agregado(anio)

            # 📊 9. Tabla de control anual
            cursor.execute("""
                INSERT INTO seul_control_anual (anio, estatus_inicio, fecha_actualizacion, estatus)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    fecha_actualizacion = VALUES(fecha_actualizacion),
                    estatus_inicio = VALUES(estatus_inicio),
                    estatus = VALUES(estatus)
            """, (anio, estatus_inicio, fecha_actualizacion, estatus))

            # ✅ EL ÚNICO COMMIT QUE IMPORTA: O se guarda todo, o no se guarda nada.
            conn.commit() 
            flash(f'Año {anio} procesado correctamente en modo {modo_carga}.', 'success')

        except Exception as e:
            conn.rollback() # Si algo falla, el DELETE del principio se deshace automáticamente
            flash(f'Error crítico: {str(e)}', 'danger')
            print(f"❌ Error en la carga: {e}")
        finally:
            cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
            cursor.close()

        return redirect(url_for('admin.subir_zip_egresos'))

    return render_template('admin/subir_zip_egresos.html')




def procesar_txt_detallado_egresos(carga_id, carpeta_destino, anio, modo_carga='agregar', bloque_size=10000):
    import csv, os
    print(f"➡️ Iniciando Procesamiento Inteligente. Año: {anio}")
    
    conn = mysql.connection
    cursor = conn.cursor()
    egresos_por_id = {}

    # 1. Función de limpieza (definida correctamente al inicio)
    def limpiar_dato(valor, columna=None):
        if valor is None:
            return None

        v = str(valor).strip()

        if v == "" or v.upper() == "NULL":
            # ⚠️ Para columnas clave, NO regreses 0
            if columna in ['CLUES', 'EGRESO']:
                return None
            return 0

        try:
            if '.' in v:
                return int(float(v))
            return v
        except:
            return None if columna in ['CLUES', 'EGRESO'] else 0

    try:
        # --- SECCIÓN EGRESOS ---
        path_egresos = None
        for root, _, files in os.walk(carpeta_destino):
            for archivo in files:
                if archivo.lower() == 'egresos.txt':
                    path_egresos = os.path.join(root, archivo)
                    break

        if path_egresos:
            with open(path_egresos, 'r', encoding='utf-8-sig') as f:
                lector = csv.DictReader(f, delimiter='|')
                columnas_txt = lector.fieldnames
                # Mapear ID a registro_id
                columnas_sql = ['registro_id' if c.upper() == 'ID' else c for c in columnas_txt]
                columnas_sql.extend(['anio', 'carga_id'])

                sql_egre = f"INSERT INTO egresos_registros ({', '.join(columnas_sql)}) VALUES ({', '.join(['%s']*len(columnas_sql))}) ON DUPLICATE KEY UPDATE carga_id = VALUES(carga_id)"

                bloque = []
                for fila_dict in lector:
                    valores = []
                    for col in columnas_txt:
                        val = limpiar_dato(fila_dict[col], col.upper())
                        # Normalizar SERVICIOEGRE
                        if col.upper() == 'SERVICIOEGRE':
                            try:
                                c_srv = int(float(val))
                                if 100 <= c_srv <= 199: val = '100'
                                elif 200 <= c_srv <= 299: val = '200'
                                elif (300 <= c_srv <= 399) or (700 <= c_srv <= 799): val = '300'
                                elif 400 <= c_srv <= 499: val = '400'
                                elif 500 <= c_srv <= 599 or 800 <= c_srv <= 999: val = '500'
                            except: pass
                        valores.append(val)

                    f_egre = fila_dict.get('EGRESO', '')
                    r_anio = fila_dict.get('ANIO') or (f_egre[:4] if len(f_egre) >= 4 else anio)
                    valores.extend([r_anio, carga_id])
                    
                    reg_id = fila_dict.get('ID')
                    if reg_id: egresos_por_id[reg_id] = r_anio
                    
                    bloque.append(tuple(valores))
                    if len(bloque) >= bloque_size:
                        cursor.executemany(sql_egre, bloque)
                        bloque = []
                if bloque: cursor.executemany(sql_egre, bloque)

        # --- SECCIÓN PROCEDIMIENTOS ---
        path_proc = None
        for root, _, files in os.walk(carpeta_destino):
            for archivo in files:
                if archivo.lower() == 'procedimientos.txt':
                    path_proc = os.path.join(root, archivo)
                    break

        if path_proc:
            with open(path_proc, 'r', encoding='utf-8-sig') as f:
                lector_p = csv.DictReader(f, delimiter='|')
                cols_p_txt = lector_p.fieldnames
                cols_p_sql = ['egreso_id' if c.upper() == 'ID' else c for c in cols_p_txt]
                
                has_anio = 'ANIO' in [c.upper() for c in cols_p_txt]
                if not has_anio: cols_p_sql.append('anio')
                cols_p_sql.append('carga_id')

                sql_proc = f"INSERT INTO procedimientos_registros ({', '.join(cols_p_sql)}) VALUES ({', '.join(['%s']*len(cols_p_sql))})"

                bloque_p = []
                for fila_p_dict in lector_p:
                    valores_p = [limpiar_dato(fila_p_dict[c]) for c in cols_p_txt]
                    if not has_anio:
                        valores_p.append(egresos_por_id.get(fila_p_dict.get('ID'), anio))
                    valores_p.append(carga_id)
                    
                    bloque_p.append(tuple(valores_p))
                    if len(bloque_p) >= bloque_size:
                        cursor.executemany(sql_proc, bloque_p)
                        bloque_p = []
                if bloque_p: cursor.executemany(sql_proc, bloque_p)

    except Exception as e:
        print(f"❌ Error en la carga: {e}")
        raise e
    finally:
        egresos_por_id.clear()

        
            
def recalcular_procedimiento_agregado(anio):
    # Usamos la conexión existente sin crear commits locales
    cursor = mysql.connection.cursor()

    try:
        # 1. Limpieza selectiva del año actual
        print(f"🧹 Limpiando datos de procedimientos para el año {anio}...")
        sql_delete = "DELETE FROM procedimiento_agregado WHERE anio = %s"
        cursor.execute(sql_delete, (anio,))

        # ===============================
        # 1️⃣ PROCEDIMIENTOS DENTRO (QUIROF = 1)
        # ===============================
        print(f"⚙️ Calculando procedimientos dentro de quirófano {anio}...")
        sql_dentro = """
            INSERT INTO procedimiento_agregado (
                clues, anio, mes,
                med_int_proced_dentro,
                cirugia_proced_dentro,
                gineco_proced_dentro,
                pediatra_proced_dentro,
                otros_proced_dentro,
                total_proced_dentro
            )
            SELECT
                e.clues,
                p.anio,
                e.MES_ESTADISTICO AS mes,
                SUM(CASE WHEN e.SERVICIOEGRE = '100' THEN 1 ELSE 0 END),
                SUM(CASE WHEN e.SERVICIOEGRE = '200' THEN 1 ELSE 0 END),
                SUM(CASE WHEN e.SERVICIOEGRE = '400' THEN 1 ELSE 0 END),
                SUM(CASE WHEN e.SERVICIOEGRE = '300' THEN 1 ELSE 0 END),
                SUM(CASE WHEN e.SERVICIOEGRE NOT IN ('100','200','300','400') THEN 1 ELSE 0 END),
                COUNT(*)
            FROM procedimientos_registros p
            JOIN egresos_registros e ON p.egreso_id = e.registro_id AND p.anio = e.anio
            WHERE p.tipo = 'Q'
              AND p.quirof = 1
              AND p.anio = %s
            GROUP BY e.clues, p.anio, e.MES_ESTADISTICO

            ON DUPLICATE KEY UPDATE
            med_int_proced_dentro = VALUES(med_int_proced_dentro),
            cirugia_proced_dentro = VALUES(cirugia_proced_dentro),
            gineco_proced_dentro = VALUES(gineco_proced_dentro),
            pediatra_proced_dentro = VALUES(pediatra_proced_dentro),
            otros_proced_dentro = VALUES(otros_proced_dentro),
            total_proced_dentro = VALUES(total_proced_dentro)
        """
        cursor.execute(sql_dentro, (anio,))

        # ===============================
        # 2️⃣ PROCEDIMIENTOS FUERA (QUIROF = 2)
        # ===============================
        print(f"⚙️ Actualizando procedimientos fuera de quirófano {anio}...")
        sql_fuera = """
            INSERT INTO procedimiento_agregado (
                clues, anio, mes,
                med_int_proced_fuera,
                cirugia_proced_fuera,
                gineco_proced_fuera,
                pediatra_proced_fuera,
                otros_proced_fuera,
                total_proced_fuera
            )
            SELECT
                e.clues,
                p.anio,
                e.MES_ESTADISTICO AS mes,
                SUM(CASE WHEN e.SERVICIOEGRE = '100' THEN 1 ELSE 0 END),
                SUM(CASE WHEN e.SERVICIOEGRE = '200' THEN 1 ELSE 0 END),
                SUM(CASE WHEN e.SERVICIOEGRE = '400' THEN 1 ELSE 0 END),
                SUM(CASE WHEN e.SERVICIOEGRE = '300' THEN 1 ELSE 0 END),
                SUM(CASE WHEN e.SERVICIOEGRE NOT IN ('100','200','300','400') THEN 1 ELSE 0 END),
                COUNT(*)
            FROM procedimientos_registros p
            JOIN egresos_registros e ON p.egreso_id = e.registro_id AND p.anio = e.anio
            WHERE p.tipo = 'Q'
              AND p.quirof = 2
              AND p.anio = %s
            GROUP BY e.clues, p.anio, e.MES_ESTADISTICO
            ON DUPLICATE KEY UPDATE
                med_int_proced_fuera = VALUES(med_int_proced_fuera),
                cirugia_proced_fuera = VALUES(cirugia_proced_fuera),
                gineco_proced_fuera = VALUES(gineco_proced_fuera),
                pediatra_proced_fuera = VALUES(pediatra_proced_fuera),
                otros_proced_fuera = VALUES(otros_proced_fuera),
                total_proced_fuera = VALUES(total_proced_fuera)
        """
        cursor.execute(sql_fuera, (anio,))

        # ===============================
        # 3️⃣ TOTALES GENERALES
        # ===============================
        sql_totales = """
            UPDATE procedimiento_agregado
            SET total_procedimientos_gen = 
                IFNULL(total_proced_dentro, 0) + IFNULL(total_proced_fuera, 0)
            WHERE anio = %s
        """
        cursor.execute(sql_totales, (anio,))

        # Eliminado: mysql.connection.commit()
        print(f"✅ Cálculos de procedimientos para {anio} preparados en memoria.")

    except Exception as e:
        # Eliminado: mysql.connection.rollback()
        print(f"❌ Error al recalcular procedimientos: {e}")
        raise e  # Lanzamos el error para que subir_zip_egresos haga el rollback global
    finally:
        # Importante: No cerramos el cursor aquí para que la siguiente función pueda seguir usándolo
        pass



def recalcular_egresos_agregado(anio):
    # Usamos el cursor de la conexión actual
    cursor = mysql.connection.cursor()
    
    try:
        print(f"🧹 Limpiando egresos_agregado para el año {anio}...")
        # Borramos los datos previos del año para evitar duplicados al insertar
        cursor.execute("DELETE FROM egresos_agregado WHERE anio = %s", (anio,))

        sql = """
        INSERT INTO egresos_agregado (
            clues, nombre_unidad, anio, mes,
            total_egresos, defunciones, defunciones_48h,
            nacimientos, cesareas, abortos, apeo, total_productos,
            total_procedimientos, dias_estancia_sum, dias_estancia_prom,
            dias_estancia_med_interna, dias_estancia_cirugia, dias_estancia_pediatria,
            dias_estancia_ginecobstetricia, dias_estancia_otros,
            prom_estancia_med_interna, prom_estancia_cirugia, prom_estancia_pediatria,
            prom_estancia_ginecobstetricia, prom_estancia_otros,
            last_updated,
            med_interna, cirugia, pediatria, ginecobstetricia, otros,

            def_48h_med_interna, def_48h_cirugia, def_48h_ginecobstetricia, def_48h_pediatria, def_48h_otros,

            defunciones_med_interna, defunciones_cirugia, defunciones_ginecobstetricia, defunciones_pediatria, defunciones_otros,

            nac_eutocico, nac_distocico, nac_cesarea,

            egresos_48h,

            adolescente_apeo, eventos_obstetricos_adolescentes, porcentaje_adolescente_apeo,

            egresos_med_interna_48h, egresos_cirugia_48h, egresos_pediatria_48h,
            egresos_ginecobstetricia_48h, egresos_otros_48h
        )

        SELECT
            IFNULL(e.CLUES, 'SIN_CLUES'),
            IFNULL(c.nombre_unidad, 'SIN NOMBRE'),
            e.anio,
            e.MES_ESTADISTICO,

            COUNT(DISTINCT e.registro_id),

            -- DEFUNCIONES
            SUM(CASE WHEN CAST(e.MOTEGRE AS UNSIGNED) = 5 THEN 1 ELSE 0 END),
            SUM(CASE WHEN CAST(e.MOTEGRE AS UNSIGNED) = 5 AND e.DIAS_ESTA > 2 THEN 1 ELSE 0 END),

            -- NACIMIENTOS
            SUM(CASE WHEN CAST(e.TIPNACI AS UNSIGNED) IN (1,2,3) THEN 1 ELSE 0 END),

            -- CESAREAS
            SUM(CASE WHEN CAST(e.TIPNACI AS UNSIGNED) = 3 THEN 1 ELSE 0 END),

            -- ABORTOS
            SUM(CASE WHEN CAST(e.TIPATEN AS UNSIGNED) = 1 THEN 1 ELSE 0 END),

            -- APEO
            SUM(CASE 
                WHEN CAST(e.TIPATEN AS UNSIGNED) IN (1,2)
                AND CAST(e.PLANFAM AS UNSIGNED) NOT IN (0,88,99)
            THEN 1 ELSE 0 END),

            -- PRODUCTOS Y PROCEDIMIENTOS
            SUM(IFNULL(e.TOTAL_PRODUCTOS, 0)),
            SUM(IFNULL(proc_sum.total_p, 0)),

            -- ESTANCIA
            SUM(e.DIAS_ESTA),
            ROUND(AVG(e.DIAS_ESTA), 2),

            -- DIAS ESTANCIA POR SERVICIO
            SUM(CASE WHEN e.SERVICIOEGRE='100' THEN e.DIAS_ESTA ELSE 0 END),
            SUM(CASE WHEN e.SERVICIOEGRE='200' THEN e.DIAS_ESTA ELSE 0 END),
            SUM(CASE WHEN e.SERVICIOEGRE='300' THEN e.DIAS_ESTA ELSE 0 END),
            SUM(CASE WHEN e.SERVICIOEGRE='400' THEN e.DIAS_ESTA ELSE 0 END),
            SUM(CASE WHEN e.SERVICIOEGRE NOT IN ('100','200','300','400')
                    THEN e.DIAS_ESTA ELSE 0 END),

            -- PROMEDIO ESTANCIA POR SERVICIO
            ROUND(AVG(CASE WHEN e.SERVICIOEGRE='100' THEN e.DIAS_ESTA END),2),
            ROUND(AVG(CASE WHEN e.SERVICIOEGRE='200' THEN e.DIAS_ESTA END),2),
            ROUND(AVG(CASE WHEN e.SERVICIOEGRE='300' THEN e.DIAS_ESTA END),2),
            ROUND(AVG(CASE WHEN e.SERVICIOEGRE='400' THEN e.DIAS_ESTA END),2),
            ROUND(AVG(CASE WHEN e.SERVICIOEGRE NOT IN ('100','200','300','400')
                        THEN e.DIAS_ESTA END),2),

            NOW(),

            -- DISTRIBUCIÓN POR SERVICIO
            SUM(CASE WHEN e.SERVICIOEGRE = '100' THEN 1 ELSE 0 END),
            SUM(CASE WHEN e.SERVICIOEGRE = '200' THEN 1 ELSE 0 END),
            SUM(CASE WHEN e.SERVICIOEGRE = '300' THEN 1 ELSE 0 END),
            SUM(CASE WHEN e.SERVICIOEGRE = '400' THEN 1 ELSE 0 END),
            SUM(CASE WHEN e.SERVICIOEGRE NOT IN ('100','200','300','400') THEN 1 ELSE 0 END),

            -- DEF 48H POR SERVICIO
            SUM(CASE WHEN e.SERVICIOEGRE='100' AND e.DIAS_ESTA>2 AND CAST(e.MOTEGRE AS UNSIGNED)=5 THEN 1 ELSE 0 END),
            SUM(CASE WHEN e.SERVICIOEGRE='200' AND e.DIAS_ESTA>2 AND CAST(e.MOTEGRE AS UNSIGNED)=5 THEN 1 ELSE 0 END),
            SUM(CASE WHEN e.SERVICIOEGRE='400' AND e.DIAS_ESTA>2 AND CAST(e.MOTEGRE AS UNSIGNED)=5 THEN 1 ELSE 0 END),
            SUM(CASE WHEN e.SERVICIOEGRE='300' AND e.DIAS_ESTA>2 AND CAST(e.MOTEGRE AS UNSIGNED)=5 THEN 1 ELSE 0 END),
            SUM(CASE WHEN e.SERVICIOEGRE NOT IN ('100','200','300','400') AND e.DIAS_ESTA>2 AND CAST(e.MOTEGRE AS UNSIGNED)=5 THEN 1 ELSE 0 END),

            -- DEFUNCIONES POR SERVICIO
            SUM(CASE WHEN e.SERVICIOEGRE='100' AND CAST(e.MOTEGRE AS UNSIGNED)=5 THEN 1 ELSE 0 END),
            SUM(CASE WHEN e.SERVICIOEGRE='200' AND CAST(e.MOTEGRE AS UNSIGNED)=5 THEN 1 ELSE 0 END),
            SUM(CASE WHEN e.SERVICIOEGRE='400' AND CAST(e.MOTEGRE AS UNSIGNED)=5 THEN 1 ELSE 0 END),
            SUM(CASE WHEN e.SERVICIOEGRE='300' AND CAST(e.MOTEGRE AS UNSIGNED)=5 THEN 1 ELSE 0 END),
            SUM(CASE WHEN e.SERVICIOEGRE NOT IN ('100','200','300','400') AND CAST(e.MOTEGRE AS UNSIGNED)=5 THEN 1 ELSE 0 END),

            -- NACIMIENTOS DETALLE
            SUM(CASE WHEN CAST(e.TIPNACI AS UNSIGNED)=1 THEN 1 ELSE 0 END),
            SUM(CASE WHEN CAST(e.TIPNACI AS UNSIGNED)=2 THEN 1 ELSE 0 END),
            SUM(CASE WHEN CAST(e.TIPNACI AS UNSIGNED)=3 THEN 1 ELSE 0 END),

            -- EGRESOS >48H
            SUM(CASE WHEN e.DIAS_ESTA > 2 THEN 1 ELSE 0 END),

            -- ADOLESCENTE APEO
            SUM(
                CASE 
                    WHEN CAST(e.TIPATEN AS UNSIGNED) IN (1,2)
                    AND CAST(e.EDAD AS UNSIGNED) BETWEEN 10 AND 19
                    AND CAST(e.CVEEDAD AS UNSIGNED) = 5
                    AND CAST(e.PLANFAM AS UNSIGNED) BETWEEN 1 AND 13
                    THEN 1 ELSE 0 
                END
            ),

            -- EVENTOS OBSTETRICOS ADOLESCENTES
            SUM(
                CASE 
                    WHEN CAST(e.TIPATEN AS UNSIGNED) IN (1,2)
                    AND CAST(e.EDAD AS UNSIGNED) BETWEEN 10 AND 19
                    AND CAST(e.CVEEDAD AS UNSIGNED) = 5
                    THEN 1 ELSE 0 
                END
            ),

            -- PORCENTAJE ADOLESCENTE APEO
            ROUND(
                (
                    SUM(
                        CASE 
                            WHEN CAST(e.TIPATEN AS UNSIGNED) IN (1,2)
                            AND CAST(e.EDAD AS UNSIGNED) BETWEEN 10 AND 19
                            AND CAST(e.CVEEDAD AS UNSIGNED) = 5
                            AND CAST(e.PLANFAM AS UNSIGNED) BETWEEN 1 AND 13
                            THEN 1 ELSE 0 
                        END
                    ) * 100.0
                ) /
                NULLIF(
                    SUM(
                        CASE
                            WHEN CAST(e.TIPATEN AS UNSIGNED) IN (1,2)
                            AND CAST(e.EDAD AS UNSIGNED) BETWEEN 10 AND 19
                            AND CAST(e.CVEEDAD AS UNSIGNED) = 5
                            THEN 1 ELSE 0 
                        END
                    ),
                0),
            2),

            -- EGRESOS >48H POR SERVICIO
            SUM(CASE WHEN e.SERVICIOEGRE='100' AND e.DIAS_ESTA>2 THEN 1 ELSE 0 END),
            SUM(CASE WHEN e.SERVICIOEGRE='200' AND e.DIAS_ESTA>2 THEN 1 ELSE 0 END),
            SUM(CASE WHEN e.SERVICIOEGRE='300' AND e.DIAS_ESTA>2 THEN 1 ELSE 0 END),
            SUM(CASE WHEN e.SERVICIOEGRE='400' AND e.DIAS_ESTA>2 THEN 1 ELSE 0 END),
            SUM(CASE WHEN e.SERVICIOEGRE NOT IN ('100','200','300','400') AND e.DIAS_ESTA>2 THEN 1 ELSE 0 END)

        FROM egresos_registros e
        LEFT JOIN catalogo_unidades c ON e.CLUES = c.clues
        LEFT JOIN (
            SELECT pr.egreso_id, pr.anio, COUNT(*) as total_p
            FROM procedimientos_registros pr
            WHERE pr.anio = %s
            GROUP BY pr.egreso_id, pr.anio
        ) proc_sum 
        ON e.registro_id = proc_sum.egreso_id AND e.anio = proc_sum.anio

        WHERE e.anio = %s

        GROUP BY 
            e.CLUES,
            c.nombre_unidad,
            e.anio,
            e.MES_ESTADISTICO;
        """
        
        cursor.execute(sql, (anio, anio))
        # Eliminado: mysql.connection.commit()
        print(f"✅ Cálculos de egresos_agregado para {anio} listos.")

    except Exception as e:
        # Eliminado: mysql.connection.rollback()
        print(f"❌ Error en recalcular_egresos_agregado: {str(e)}")
        raise e # Relanzamos para activar el rollback global
    finally:
        # No cerramos el cursor aquí para evitar que falle el proceso final en la ruta principal
        pass


#********************************************************
#*************  SUBIR SINERHIAS *************************
#********************************************************

@admin.route('/sinerhias', methods=['GET', 'POST'])
@login_required
def subir_sinerhias():

    if request.method == 'POST':

        # 📌 Datos del formulario
        anio = int(request.form.get("anio"))
        modo_carga = request.form.get("modo_carga")
        estatus_inicio = request.form.get("estatus_inicio")
        fecha_actualizacion = request.form.get("fecha_actualizacion")
        estatus = request.form.get("estatus")

        if 'file' not in request.files:
            flash('No hay archivo en la solicitud', 'danger')
            return redirect(url_for('admin.subir_sinerhias'))

        file = request.files['file']

        if file.filename == '':
            flash('No se seleccionó ningún archivo', 'danger')
            return redirect(url_for('admin.subir_sinerhias'))

        if not file.filename.endswith('.xlsx'):
            flash('Solo se permiten archivos .xlsx', 'danger')
            return redirect(url_for('admin.subir_sinerhias'))

        filename = secure_filename(file.filename)

        carpeta_nombre = f"sinerhias_{anio}"
        carpeta_destino = os.path.join(
            current_app.root_path,
            'uploads',
            carpeta_nombre
        )

        # 🔥 Si es actualizar → limpiar carpeta
        if modo_carga == 'actualizar' and os.path.exists(carpeta_destino):
            shutil.rmtree(carpeta_destino)

        os.makedirs(carpeta_destino, exist_ok=True)

        filepath = os.path.join(carpeta_destino, filename)
        file.save(filepath)

        try:

            # 📖 Leer Excel
            df = pd.read_excel(filepath)
            df.columns = [c.lower().strip() for c in df.columns]

            # Validar columnas obligatorias
            columnas_requeridas = [
                'clues',
                'mes'
            ]

            faltantes = [
                col for col in columnas_requeridas
                if col not in df.columns
            ]

            if faltantes:
                flash(
                    f'Faltan columnas obligatorias en el Excel: {", ".join(faltantes)}',
                    'danger'
                )
                return redirect(url_for('admin.subir_sinerhias'))

            conn = mysql.connection
            cursor = conn.cursor()

            # 🔥 Reemplazar información del año completo
            if modo_carga == 'actualizar':
                cursor.execute(
                    "DELETE FROM sinerhias WHERE anio = %s",
                    (anio,)
                )

            insertados = 0
            omitidos = []

            for _, row in df.iterrows():

                clues = str(row['clues']).strip().upper()

                try:
                    mes = int(row['mes'])
                except:
                    omitidos.append(f"{clues} (mes inválido)")
                    continue

                # Validar rango de mes
                if mes < 1 or mes > 12:
                    omitidos.append(f"{clues} (mes {mes} inválido)")
                    continue

                cursor.execute(
                    """
                    SELECT 1
                    FROM egresos_registros
                    WHERE clues = %s
                    LIMIT 1
                    """,
                    (clues,)
                )

                if cursor.fetchone():

                    cursor.execute("""
                        INSERT INTO sinerhias (
                            clues,
                            anio,
                            mes,
                            med_int,
                            cirugia,
                            gineco,
                            pediatria,
                            otros,
                            quirofanos,
                            total,
                            salas_expulsion
                        )
                        VALUES (
                            %s,%s,%s,%s,%s,
                            %s,%s,%s,%s,%s,%s
                        )
                    """, (
                        clues,
                        anio,
                        mes,
                        row.get('med_int', 0),
                        row.get('cirugia', 0),
                        row.get('gineco', 0),
                        row.get('pediatria', 0),
                        row.get('otros', 0),
                        row.get('quirofanos', 0),
                        row.get('total', 0),
                        row.get('salas_expulsion', 0)
                    ))

                    insertados += 1

                else:
                    omitidos.append(clues)

            # 🧠 CONTROL ANUAL
            cursor.execute("""
                INSERT INTO sinerhias_control_anual
                    (
                        anio,
                        estatus_inicio,
                        fecha_actualizacion,
                        estatus
                    )
                VALUES (%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE
                    estatus_inicio = VALUES(estatus_inicio),
                    fecha_actualizacion = VALUES(fecha_actualizacion),
                    estatus = VALUES(estatus)
            """, (
                anio,
                estatus_inicio,
                fecha_actualizacion,
                estatus
            ))

            conn.commit()
            cursor.close()

            mensaje = (
                f"✔ Se insertaron {insertados} registros "
                f"para el año {anio}."
            )

            if omitidos:
                mensaje += (
                    f" ⚠ {len(omitidos)} registros omitidos."
                )

            flash(mensaje, 'success')
            return redirect(url_for('admin.subir_sinerhias'))

        except Exception as e:
            flash(f'Error al procesar el archivo: {e}', 'danger')
            return redirect(url_for('admin.subir_sinerhias'))

    return render_template('admin/subir_sinerhias.html')


# Subir camas no censables

@admin.route('/subir-camas-no-censables', methods=['GET', 'POST'])
@login_required
def subir_camas_no_censables():
    if request.method == 'POST':
        # 📌 Datos del formulario
        anio = int(request.form.get("anio"))
        modo_carga = request.form.get("modo_carga")
        # Estos campos son para tu tabla de control anual (opcional)
        estatus_inicio = request.form.get("estatus_inicio")
        fecha_actualizacion = request.form.get("fecha_actualizacion")
        estatus = request.form.get("estatus")

        if 'file' not in request.files:
            flash('No hay archivo en la solicitud', 'danger')
            return redirect(url_for('subir_camas_no_censables'))

        file = request.files['file']
        if file.filename == '' or not file.filename.endswith('.xlsx'):
            flash('Seleccione un archivo .xlsx válido', 'danger')
            return redirect(url_for('subir_camas_no_censables'))

        filename = secure_filename(file.filename)
        carpeta_destino = os.path.join(current_app.root_path, 'uploads', f"camas_{anio}")
        
        if modo_carga == 'actualizar' and os.path.exists(carpeta_destino):
            shutil.rmtree(carpeta_destino)
        
        os.makedirs(carpeta_destino, exist_ok=True)
        filepath = os.path.join(carpeta_destino, filename)
        file.save(filepath)

        try:
            # Leer Excel y normalizar nombres de columnas (minúsculas y sin espacios)
            df = pd.read_excel(filepath)
            df.columns = [c.lower().strip() for c in df.columns]

            conn = mysql.connection
            cursor = conn.cursor()

            # 🔥 Si es actualizar → borrar los registros de ese año antes de reinsertar
            if modo_carga == 'actualizar':
                cursor.execute("DELETE FROM camas_no_censables WHERE anio = %s", (anio,))

            insertados = 0
            omitidos = []

            for _, row in df.iterrows():
                clues = str(row['clues']).strip().upper()

                # Validar que la CLUES exista en tu catálogo para evitar error de Llave Foránea
                cursor.execute("SELECT 1 FROM catalogo_unidades WHERE clues = %s LIMIT 1", (clues,))
                
                if cursor.fetchone():
                    cursor.execute("""
                        INSERT INTO camas_no_censables (
                            anio, clues, 
                            hab_urgencias, inh_urgencias, tot_urgencias,
                            hab_observacion, inh_observacion, tot_observacion,
                            hab_cuid_int, inh_cuid_int, tot_cuid_int,
                            hab_cirug_amb, inh_cirug_amb, tot_cirug_amb,
                            hab_quemados, inh_quemados, tot_quemados,
                            hab_lab_parto, inh_lab_parto, tot_lab_parto,
                            hab_recup_pp, inh_recup_pp, tot_recup_pp,
                            hab_recup_pq, inh_recup_pq, tot_recup_pq,
                            hab_uci_adulto, inh_uci_adulto, tot_uci_adulto,
                            hab_uci_ped, inh_uci_ped, tot_uci_ped,
                            hab_otras_areas, inh_otras_areas, tot_otras_areas
                        )
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """, (
                        anio, clues,
                        row.get('hab_urgencias', 0), row.get('inh_urgencias', 0), row.get('tot_urgencias', 0),
                        row.get('hab_observacion', 0), row.get('inh_observacion', 0), row.get('tot_observacion', 0),
                        row.get('hab_cuid_int', 0), row.get('inh_cuid_int', 0), row.get('tot_cuid_int', 0),
                        row.get('hab_cirug_amb', 0), row.get('inh_cirug_amb', 0), row.get('tot_cirug_amb', 0),
                        row.get('hab_quemados', 0), row.get('inh_quemados', 0), row.get('tot_quemados', 0),
                        row.get('hab_lab_parto', 0), row.get('inh_lab_parto', 0), row.get('tot_lab_parto', 0),
                        row.get('hab_recup_pp', 0), row.get('inh_recup_pp', 0), row.get('tot_recup_pp', 0),
                        row.get('hab_recup_pq', 0), row.get('inh_recup_pq', 0), row.get('tot_recup_pq', 0),
                        row.get('hab_uci_adulto', 0), row.get('inh_uci_adulto', 0), row.get('tot_uci_adulto', 0),
                        row.get('hab_uci_ped', 0), row.get('inh_uci_ped', 0), row.get('tot_uci_ped', 0),
                        row.get('hab_otras_areas', 0), row.get('inh_otras_areas', 0), row.get('tot_otras_areas', 0)
                    ))
                    insertados += 1
                else:
                    omitidos.append(clues)

            # 🧠 Registro en tabla de control (para saber cuándo se subió el año)
            # Nota: Asegúrate de que la tabla 'camas_control_anual' exista o cámbiale el nombre
            cursor.execute("""
                INSERT INTO sinerhias_control_anual (anio, estatus_inicio, fecha_actualizacion, estatus)
                VALUES (%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE
                    estatus_inicio = VALUES(estatus_inicio),
                    fecha_actualizacion = VALUES(fecha_actualizacion),
                    estatus = VALUES(estatus)
            """, (anio, estatus_inicio, fecha_actualizacion, estatus))

            conn.commit()
            cursor.close()

            mensaje = f"✔ Se procesaron {insertados} unidades para el año {anio}."
            if omitidos:
                mensaje += f" ⚠ {len(omitidos)} CLUES no se encontraron en el catálogo."

            flash(mensaje, 'success')
            return redirect(url_for('subir_camas_no_censables'))

        except Exception as e:
            flash(f'Error crítico al procesar: {e}', 'danger')
            return redirect(url_for('subir_camas_no_censables'))

    return render_template('admin/subir_camas_no_censables.html')



# Subir equipo medico

@admin.route('/subir-equipo-medico', methods=['GET', 'POST'])
@login_required
def subir_equipo_medico():
    if request.method == 'POST':
        anio = int(request.form.get("anio"))
        modo_carga = request.form.get("modo_carga")
        # Datos de control
        estatus_inicio = request.form.get("estatus_inicio")
        fecha_actualizacion = request.form.get("fecha_actualizacion")
        estatus = request.form.get("estatus")

        if 'file' not in request.files:
            flash('No hay archivo en la solicitud', 'danger')
            return redirect(url_for('subir_equipo_medico'))

        file = request.files['file']
        if file.filename == '' or not file.filename.endswith('.xlsx'):
            flash('Seleccione un archivo .xlsx válido', 'danger')
            return redirect(url_for('subir_equipo_medico'))

        filename = secure_filename(file.filename)
        carpeta_destino = os.path.join(current_app.root_path, 'uploads', f"equipo_{anio}")
        
        if modo_carga == 'actualizar' and os.path.exists(carpeta_destino):
            shutil.rmtree(carpeta_destino)
        
        os.makedirs(carpeta_destino, exist_ok=True)
        filepath = os.path.join(carpeta_destino, filename)
        file.save(filepath)

        try:
            # 1. Leer Excel y limpiar nombres de columnas
            df = pd.read_excel(filepath)
            df.columns = [c.lower().strip() for c in df.columns]

            conn = mysql.connection
            cursor = conn.cursor()

            # 2. Limpieza si es actualización
            if modo_carga == 'actualizar':
                cursor.execute("DELETE FROM equipo_medico WHERE anio = %s", (anio,))

            # 3. Definir la lista de columnas de equipo médico (las que definimos antes)
            # Esto evita intentar insertar columnas que no existen en la DB (como 'nombre unidad')
            columnas_equipo = [
                'mes',
                'arco_c_analogo', 'arco_c_digital', 'bascula_estadimetro', 'bascula_bebe',
                'camilla_radiotransp', 'cardiotocografo', 'carro_rojo_reanim', 'cuna_calor_rad',
                'cuna_calor_rad_foto', 'defibrilador_monit', 'ecocardiografo', 'electrocardiografo',
                'estuche_diag', 'incubadora_fototer', 'incubadora_trasl', 'incubadora_cuidados',
                'lampara_quirurgica_doble', 'lampara_quir_port', 'lampara_quir_senc', 'mesa_quir_obs',
                'mesa_exploracion', 'mesa_quir_gral', 'microscopio_rutina', 'monitor_radiacion',
                'monitor_signos_vit_avanz', 'monitor_signos_neo', 'monitor_signos_bas', 'monitor_traslado',
                'monitor_signos_int', 'monitor_signos_vit_neona', 'monitor_anestesia', 'negatoscopio',
                'refrige_lab', 'sierra_yesos', 'ultrasonido_diag', 'unidad_anestesia_bas', 'ultrasonido_terap',
                'unidad_dental', 'unidad_rx_analogo', 'unidad_rx_dental', 'unidad_rx_digital',
                'unidad_rx_port_ana', 'unidad_rx_port_dig', 'fluoroscopio_dig', 'fluoroscopio_dig_analog',
                'mastografo_digital', 'mastografo_estereo', 'mastografo_estereo_tomosin', 'microscopio_cirugia',
                'resonancia_mag', 'tomografo_128', 'tomografo_16', 'tomografo_32', 'tomografo_64'
            ]

            insertados = 0
            omitidos = []

            for _, row in df.iterrows():
                clues = str(row['clues']).strip().upper()

                # Validar existencia de CLUES
                cursor.execute("SELECT 1 FROM catalogo_unidades WHERE clues = %s LIMIT 1", (clues,))
                
                if cursor.fetchone():
                    # --- CONSTRUCCIÓN DINÁMICA DEL QUERY ---
                    # Solo tomamos las columnas que existan en el row del excel
                    cols_presentes = ['anio', 'clues'] + [
                        c for c in columnas_equipo
                        if c in df.columns and c.isidentifier()
                    ]

                    placeholders = ", ".join(["%s"] * len(cols_presentes))
                    nombres_cols = ", ".join(f"`{c}`" for c in cols_presentes)
                    valores = [anio, clues]
                    for c in cols_presentes[2:]:
                        val = row.get(c)

                        if pd.isna(val):
                            valores.append(None if c == "mes" else 0)
                        else:
                            valores.append(int(float(val)))

                    query = f"INSERT INTO equipo_medico ({nombres_cols}) VALUES ({placeholders})"
                    cursor.execute(query, tuple(valores))
                    
                    insertados += 1
                else:
                    omitidos.append(clues)

            # 4. Registro en control anual (opcional pero recomendado)
            cursor.execute("""
                INSERT INTO sinerhias_control_anual (anio, estatus_inicio, fecha_actualizacion, estatus)
                VALUES (%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE
                    estatus_inicio = VALUES(estatus_inicio),
                    fecha_actualizacion = VALUES(fecha_actualizacion),
                    estatus = VALUES(estatus)
            """, (anio, estatus_inicio, fecha_actualizacion, estatus))

            conn.commit()
            cursor.close()

            mensaje = f"✔ Se procesaron {insertados} registros de equipo médico para {anio}."
            if omitidos:
                mensaje += f" ⚠ {len(omitidos)} CLUES no encontradas."

            flash(mensaje, 'success')
            return redirect(url_for('admin.subir_equipo_medico'))

        except Exception as e:
            flash(f'Error al procesar el Excel: {e}', 'danger')
            return redirect(url_for('subir_equipo_medico'))

    return render_template('admin/subir_equipo_medico.html')




@admin.route('/cargas', methods=['GET'])
@login_required
def listar_cargas():
    cursor = mysql.connection.cursor(dictionary=True)
    cursor.execute("SELECT * FROM cargas_zip ORDER BY fecha_carga DESC")
    cargas = cursor.fetchall()
    cursor.close()
    return render_template('admin/listar_cargas.html', cargas=cargas)

@admin.route('/activar_carga/<int:carga_id>', methods=['POST'])
@login_required
def activar_carga(carga_id):
    cursor = mysql.connection.cursor()

    # Marcar todas como inactivas primero
    cursor.execute("UPDATE cargas_zip SET estado = 'inactiva'")

    # Activar la seleccionada
    cursor.execute("UPDATE cargas_zip SET estado = 'activa' WHERE id = %s", (carga_id,))
    
    mysql.connection.commit()
    cursor.close()

    flash('Carga activada correctamente.')
    return redirect(url_for('admin.listar_cargas'))

@admin.route('/reportes')
def vista_reportes():
    cursor = mysql.connection.cursor()
    anios_disponibles = []
    unidades_disponibles = []

    # ===================== AÑOS DISPONIBLES (SIMPLE Y DIRECTO) =====================
    try:
        # 1. urgencias_agregado → 'anio'
        cursor.execute("SELECT DISTINCT anio FROM urgencias_agregado WHERE anio IS NOT NULL ORDER BY anio")
        anios_urg = [row[0] for row in cursor.fetchall()]

        # 2. egresos_registros → 'anio' (¡YA EXISTE!)
        cursor.execute("SELECT DISTINCT anio FROM egresos_registros WHERE anio IS NOT NULL ORDER BY anio")
        anios_egr = [row[0] for row in cursor.fetchall()]

        # Combinar sin duplicados
        anios_disponibles = sorted(list(set(anios_urg + anios_egr)))

    except Exception as e:
        print("Error al obtener años:", e)
        # Fallback seguro
        cursor.execute("SELECT DISTINCT anio FROM urgencias_agregado ORDER BY anio")
        anios_disponibles = [row[0] for row in cursor.fetchall()]

    # ===================== UNIDADES DISPONIBLES =====================
    try:
        # 1. urgencias → 'nombre_unidad'
        cursor.execute("SELECT DISTINCT nombre_unidad FROM urgencias_agregado WHERE nombre_unidad IS NOT NULL AND TRIM(nombre_unidad) != ''")
        unidades_urg = [row[0].strip() for row in cursor.fetchall()]

        # 2. egresos → 'CLUES' (es el identificador)
        cursor.execute("SELECT DISTINCT CLUES FROM egresos_registros WHERE CLUES IS NOT NULL AND TRIM(CLUES) != ''")
        clues_egr = [row[0].strip() for row in cursor.fetchall()]

        # OPCIÓN: Si tienes catálogo de CLUES → Nombre, úsalo aquí
        # Pero por ahora: usar CLUES como "unidad"
        unidades_egr = clues_egr

        # Combinar
        unidades_disponibles = sorted(list(set(unidades_urg + unidades_egr)))

    except Exception as e:
        print("Error al obtener unidades:", e)
        cursor.execute("SELECT DISTINCT nombre_unidad FROM urgencias_agregado ORDER BY nombre_unidad")
        unidades_disponibles = [row[0] for row in cursor.fetchall()]

    cursor.close()

    return render_template(
        'reportes/reporte.html',
        anios_disponibles=anios_disponibles or [2023, 2024, 2025],
        unidades_disponibles=unidades_disponibles or []
    )



#********************************************************************
#*****************  CARGAR BASES SIS ********************************
#********************************************************************

@admin.route("/subir_csv_sis", methods=["GET", "POST"])
@login_required
def subir_csv_sis():
   
    if request.method == "POST":
        # 📌 1. Obtención de datos
        file = request.files.get("file")
        anio = request.form.get("anio")
        modo = request.form.get("modo_carga")
        fecha_actualizacion = request.form.get("fecha_actualizacion")
        estatus = request.form.get("estatus")
        estatus_inicio = request.form.get("estatus_inicio")

        if not file or not anio:
            flash("Falta el archivo o el año", "danger")
            return redirect(url_for('subir_csv_sis'))
        
        anio = int(anio)

        try:
            # 📖 2. Lectura y Normalización
            df = pd.read_csv(file, dtype=str) 
            df.columns = [col.strip().lower().replace(" ", "_").replace("ó","o") for col in df.columns]

            conn = mysql.connection
            cursor = conn.cursor()

            # 🏥 3. Filtro de Catálogo (Solo unidades autorizadas)
            cursor.execute("SELECT clues FROM catalogo_unidades")
            clues_validas = set(row[0].upper().strip() for row in cursor.fetchall())

            if 'clues' in df.columns:
                df['clues'] = df['clues'].str.upper().str.strip()
                df = df[df['clues'].isin(clues_validas)].copy()

            # 🧹 4. Limpieza de Datos Críticos
            if "total" in df.columns:
                # Quitamos comas y convertimos a numérico, errores a 0
                df["total"] = df["total"].str.replace(",", "").fillna("0")
            
            if "apartado" in df.columns:
                df["apartado"] = df["apartado"].str[:3]
            if "variable" in df.columns:
                df["variable"] = df["variable"].str[:5]
            
            df["anio"] = anio
            df = df.where(pd.notnull(df), None)

            # 🔓 5. Operaciones de Base de Datos
            cursor.execute("SET FOREIGN_KEY_CHECKS = 0")

            # 🔥 Borrado preventivo
            if modo in ["actualizar", "reemplazar"]:
                cursor.execute("DELETE FROM sis_registros WHERE anio = %s", (anio,))
                cursor.execute("DELETE FROM sis_registros_agregados WHERE anio = %s", (anio,))
                print(f"🧹 Limpieza SIS año {anio} completada.")

            # 🚀 6. Inserción por Bloques (Eficiencia)
            columnas_db = ['anio', 'jurisdiccion', 'municipio', 'clues', 'mes', 'apartado', 'variable', 'total']
            for col in columnas_db:
                if col not in df.columns: df[col] = None

            df_final = df[columnas_db]

            df_final = df_final.replace({np.nan: None})
            df_final = df_final.where(pd.notnull(df_final), None)

            valores = [
                tuple(None if pd.isna(x) else x for x in row)
                for row in df_final.to_numpy()
            ]
            
            sql_ins = f"INSERT INTO sis_registros ({', '.join(columnas_db)}) VALUES ({', '.join(['%s']*len(columnas_db))})"
            
            bloque_size = 10000
            for i in range(0, len(valores), bloque_size):
                cursor.executemany(sql_ins, valores[i : i + bloque_size])

            # ⚙️ 7. Recálculo de Agregados SIS
            cursor.execute("""
                INSERT INTO sis_registros_agregados (
                    anio, mes, clues, nombre_unidad,
                    consultas, especialidad, mental, bucal, diasPaciente,
                    no_medicas, med_interna, cirugia, gineco, pediatria,
                    otros, psiquiatria,
                    laboratorio, rayosx, anatomia, electro, encefa,
                    ultrasonido, tac, rnm, medicas
                )
                SELECT
                    sr.anio, sr.mes, sr.clues, cu.nombre_unidad,
                    SUM(CASE WHEN sr.variable IN ('CON01','CON02','CON03','CON04','CON05','CON06','CON07','CON08','CON09','CON10',
                        'CON11','CON12','CON13','CON14','CON15','CON16','CON17','CON18','CON19','CON20',
                        'CON21','CON22','CON23','CON24','CON25','CON26','CON27','CON28','CON29','CON30',
                        'CON31','CON32','CON33','CON34','CON35','CON36','CON37','CON38','CON39','CON40',
                        'CON41','CON42','CON43','CON44','CON45','CON46','CON47','COD01','COD02')
                    THEN CAST(sr.total AS UNSIGNED) ELSE 0 END),
                    SUM(CASE WHEN sr.variable IN (
                        'CES01','CES02','CES03','CES04','CES05','CES06','CES07',
                        'CES08','CES09','CES10','CES11','CES12','CES13','CES14',
                        'CES15','CES16','CES17','CES18',
                        'HPC03','HPC04','HPC05','HPC08','HPC10','HPC11','HPC12',
                        'HPC15','HPC17','HPC18','HPC19','HPC22','HPC24','HPC25',
                        'HPC26','HPC29')
                    THEN CAST(sr.total AS UNSIGNED) ELSE 0 END),
                    SUM(CASE WHEN sr.variable IN ('CPP07','CPP14','HPC06','HPC13','HPC20','HPC27') THEN CAST(sr.total AS UNSIGNED) ELSE 0 END),
                    SUM(CASE WHEN sr.variable IN ('CPP06','CPP13','HPC09','HPC16','HPC23','HPC30','COD01','COD02') THEN CAST(sr.total AS UNSIGNED) ELSE 0 END),
                    SUM(CASE WHEN sr.variable IN ('HOS01','HOS02','HOS03','HOS04','HOS05','HPH12') THEN CAST(sr.total AS UNSIGNED) ELSE 0 END),
                    SUM(CASE WHEN sr.variable IN (
                        'CNM01','CNM02','CNM03','CNM04','CNM05','CNM06','CNM07','CNM08','CNM09','CNM10',
                        'CNM11','CNM12','CNM13','CNM14','CNM15','CNM16','CNM17','CNM18','CNM19','CNM20',
                        'CNM21','CNM22','CNM23','CNM24','CNM25','CNM26','CNM27','CNM28','CNM29','CNM30',
                        'CNM31','CNM32','CNM33','CNM34','CNM35','CNM36','CNM37')
                    THEN CAST(sr.total AS UNSIGNED) ELSE 0 END),
                    SUM(CASE WHEN sr.variable = 'HOS02' THEN CAST(sr.total AS UNSIGNED) ELSE 0 END),
                    SUM(CASE WHEN sr.variable = 'HOS01' THEN CAST(sr.total AS UNSIGNED) ELSE 0 END),
                    SUM(CASE WHEN sr.variable = 'HOS04' THEN CAST(sr.total AS UNSIGNED) ELSE 0 END),
                    SUM(CASE WHEN sr.variable = 'HOS03' THEN CAST(sr.total AS UNSIGNED) ELSE 0 END),
                    SUM(CASE WHEN sr.variable = 'HOS05' THEN CAST(sr.total AS UNSIGNED) ELSE 0 END),
                    SUM(CASE WHEN sr.variable = 'HPH12' THEN CAST(sr.total AS UNSIGNED) ELSE 0 END),
                    SUM(CASE WHEN sr.variable = 'LAB01' THEN CAST(sr.total AS UNSIGNED) ELSE 0 END),
                    SUM(CASE WHEN sr.variable = 'LRX01' THEN CAST(sr.total AS UNSIGNED) ELSE 0 END),
                    SUM(CASE WHEN sr.variable = 'LAP01' THEN CAST(sr.total AS UNSIGNED) ELSE 0 END),
                    SUM(CASE WHEN sr.variable = 'LOE01' THEN CAST(sr.total AS UNSIGNED) ELSE 0 END),
                    SUM(CASE WHEN sr.variable IN ('LEN01','HPE10') THEN CAST(sr.total AS UNSIGNED) ELSE 0 END),
                    SUM(CASE WHEN sr.variable = 'LUS01' THEN CAST(sr.total AS UNSIGNED) ELSE 0 END),
                    SUM(CASE WHEN sr.variable = 'LTC01' THEN CAST(sr.total AS UNSIGNED) ELSE 0 END),
                    SUM(CASE WHEN sr.variable = 'RSM01' THEN CAST(sr.total AS UNSIGNED) ELSE 0 END),
                    (
                        SUM(CASE WHEN sr.variable IN ('CON01','CON02','CON03','CON04','CON05','CON06','CON07','CON08','CON09','CON10','CON11','CON12','CON13','CON14','CON15','CON16','CON17','CON18','CON19','CON20','CON21','CON22','CON23','CON24','CON25','CON26','CON27','CON28','CON29','CON30','CON31','CON32','CON33','CON34','CON35','CON36','CON37','CON38','CON39','CON40','CON41','CON42','CON43','CON44','CON45','CON46','CON47','COD01','COD02') THEN CAST(sr.total AS UNSIGNED) ELSE 0 END)
                        -
                        (
                            SUM(CASE WHEN sr.variable IN ('CES01','CES02','CES03','CES04','CES05','CES06','CES07','CES08','CES09','CES10','CES11','CES12','CES13','CES14','CES15','CES16','CES17','CES18','HPC03','HPC04','HPC05','HPC08','HPC10','HPC11','HPC12','HPC15','HPC17','HPC18','HPC19','HPC22','HPC24','HPC25','HPC26','HPC29') THEN CAST(sr.total AS UNSIGNED) ELSE 0 END) +
                            SUM(CASE WHEN sr.variable IN ('CPP07','CPP14','HPC06','HPC13','HPC20','HPC27') THEN CAST(sr.total AS UNSIGNED) ELSE 0 END) +
                            SUM(CASE WHEN sr.variable IN ('CPP06','CPP13','HPC09','HPC16','HPC23','HPC30','COD01','COD02') THEN CAST(sr.total AS UNSIGNED) ELSE 0 END) +
                            SUM(CASE WHEN sr.variable IN ('CNM01','CNM02','CNM03','CNM04','CNM05','CNM06','CNM07','CNM08','CNM09','CNM10','CNM11','CNM12','CNM13','CNM14','CNM15','CNM16','CNM17','CNM18','CNM19','CNM20','CNM21','CNM22','CNM23','CNM24','CNM25','CNM26','CNM27','CNM28','CNM29','CNM30','CNM31','CNM32','CNM33','CNM34','CNM35','CNM36','CNM37') THEN CAST(sr.total AS UNSIGNED) ELSE 0 END)
                        )
                    )
                FROM sis_registros sr
                LEFT JOIN catalogo_unidades cu ON sr.clues = cu.clues
                WHERE sr.anio = %s
                GROUP BY sr.anio, sr.mes, sr.clues, cu.nombre_unidad
            """, (anio,))

            # 📊 8. Control Anual (Actualiza el encabezado)
            cursor.execute("""
                INSERT INTO sis_control_anual (anio, estatus_inicio, fecha_actualizacion, estatus)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    fecha_actualizacion = VALUES(fecha_actualizacion),
                    estatus_inicio = VALUES(estatus_inicio),
                    estatus = VALUES(estatus)
            """, (anio, estatus_inicio, fecha_actualizacion, estatus))

            # ✅ 9. COMMIT FINAL
            conn.commit()
            flash(f"Base SIS {anio} procesada con éxito (Filtrada por catálogo).", "success")

        except Exception as e:
            if 'conn' in locals(): conn.rollback()
            flash(f"Error al procesar SIS: {str(e)}", "danger")
            print(f"❌ Error SIS: {e}")
        finally:
            if 'cursor' in locals():
                cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
                cursor.close()

        return redirect(url_for('admin.subir_csv_sis'))

    return render_template("admin/subir_csv_sis.html")


#*****************************************************************
#**********  CARGAR AGENDAS **************************************
#*****************************************************************

@admin.route('/subir-imagenes-agenda', methods=['GET', 'POST'])
@login_required
def subir_imagenes_agenda():
    if request.method == 'POST':
        # Nota: Asegúrate de que el input en tu HTML tenga multiple
        archivos = request.files.getlist('carpeta_imagenes')
        
        # Ajustamos la ruta destino a la carpeta de imágenes
        ruta_destino = os.path.join(current_app.root_path, 'static', 'img', 'agenda')

        archivos_ordenados = sorted(archivos, key=lambda x: x.filename)
        
        # 1. Limpieza de imágenes previas
        if os.path.exists(ruta_destino):
            shutil.rmtree(ruta_destino)
        os.makedirs(ruta_destino)
        
        # 2. Procesar imágenes
        count = 0
        for archivo in archivos:
            if archivo and archivo.filename.lower().endswith(('.webp', '.jpg', '.jpeg', '.png')):
               
                nombre_base = os.path.basename(archivo.filename)    
                nombre_limpio = nombre_base.replace('/', '_').replace('\\', '_').replace(' ', '_')    
                nombre_seguro = secure_filename(nombre_limpio)
                ruta_final = os.path.join(ruta_destino, nombre_seguro)
                archivo.save(ruta_final)
                count += 1
        
        flash(f'¡Éxito! Se han guardado {count} imágenes para el libro.', 'success')
        return redirect(url_for('admin.subir_imagenes_agenda'))
        
    return render_template('admin/subir_imagenes_agenda.html')



@admin.route('/eliminar-imagenes-agenda', methods=['POST'])
def eliminar_imagenes_agenda():
    # Esto detecta automáticamente /var/www/html/indicador_hospitalario/static/img/agenda
    base_dir = current_app.root_path
    folder_path = os.path.join(base_dir, 'static', 'img', 'agenda')
    
    # Debug: Imprime en la consola del servidor para ver dónde está buscando realmente
    print(f"Buscando carpeta en: {folder_path}")

    try:
        if os.path.exists(folder_path):
            # Limpiamos el contenido sin borrar la carpeta 'agenda' misma
            for filename in os.listdir(folder_path):
                file_path = os.path.join(folder_path, filename)
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            
            flash('Imágenes eliminadas correctamente.', 'success')
        else:
            # Si no existe, la creamos para evitar futuros errores
            os.makedirs(folder_path, exist_ok=True)
            flash('La carpeta no existía, pero ha sido creada.', 'info')
            
    except Exception as e:
        flash(f'Error de permisos o sistema: {str(e)}', 'danger')

    # IMPORTANTE: Verifica que 'admin.subir_imagenes_agenda' sea la función 
    # que renderiza el formulario original.
    return redirect(url_for('admin.subir_imagenes_agenda'))




@admin.route('/upload_abortos', methods=['GET', 'POST'])
@login_required
def subir_csv_abortos():
    if request.method == 'POST':

        file = request.files.get("file")
        anio = request.form.get("anio")
        modo = request.form.get("modo_carga")

        if not file or not anio:
            flash("Falta archivo o año", "danger")
            return redirect(url_for('subir_csv_abortos'))

        anio = int(anio)

        try:
            # ============================
            # 📖 Leer CSV
            # ============================
            df = pd.read_csv(file, dtype=str)

            # Normalizar columnas
            df.columns = [
                col.strip().lower()
                .replace(" ", "_")
                .replace("ó", "o")
                for col in df.columns
            ]

            # ============================
            # 🧹 Limpieza
            # ============================
            df["anio"] = anio

            # Limpiar números
            for col in ["lui", "ameu", "medicamento", "no_especificado", "total"]:
                if col in df.columns:
                    df[col] = df[col].str.replace(",", "").fillna("0")

            # Limpiar claves
            if "clues" in df.columns:
                df["clues"] = df["clues"].str.upper().str.strip()

            # ============================
            # 🏥 Filtrar por catálogo
            # ============================
            conn = mysql.connection
            cursor = conn.cursor()

            cursor.execute("SELECT clues FROM catalogo_unidades")
            claves_validas = set(row[0].upper().strip() for row in cursor.fetchall())

            df = df[df["clues"].isin(claves_validas)].copy()

            # ============================
            # 🔓 DB
            # ============================
            cursor.execute("SET FOREIGN_KEY_CHECKS = 0")

            if modo in ["actualizar", "reemplazar"]:
                cursor.execute("DELETE FROM abortos WHERE anio = %s", (anio,))

            # ============================
            # 🚀 Insertar en bloques
            # ============================
            columnas_db = [
                "anio", "jurisdiccion", "municipio", "clues", "mes",
                "lui", "ameu", "medicamento", "no_especificado", "total"
            ]

            # Asegurar columnas
            for col in columnas_db:
                if col not in df.columns:
                    df[col] = None

            df_final = df[columnas_db]

            valores = [tuple(x) for x in df_final.to_numpy()]

            sql = f"""
                INSERT INTO abortos ({', '.join(columnas_db)})
                VALUES ({', '.join(['%s'] * len(columnas_db))})
            """

            bloque = 10000
            for i in range(0, len(valores), bloque):
                cursor.executemany(sql, valores[i:i + bloque])

            conn.commit()

            flash(f"Abortos {anio} cargado correctamente", "success")

        except Exception as e:
            conn.rollback()
            flash(f"Error: {str(e)}", "danger")
            print(f"❌ Error abortos: {e}")

        finally:
            cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
            cursor.close()

        return redirect(url_for('admin.subir_csv_abortos'))

    return render_template('admin/subir_csv_abortos.html')



@admin.route('/upload_afecciones_morbi', methods=['GET', 'POST'])
@login_required
def subir_csv_afecciones_morbi():
    if request.method == 'POST':

        file = request.files.get("file")
        anio = request.form.get("anio")
        modo = request.form.get("modo_carga")

        if not file or not anio:
            flash("Falta archivo o año", "danger")
            return redirect(url_for('subir_csv_afecciones_morbi'))

        anio = int(anio)

        try:
            # ============================
            # 📖 Leer CSV
            # ============================
            df = pd.read_csv(file, dtype=str)

            # Normalizar columnas
            df.columns = [
                col.strip().lower()
                .replace(" ", "_")
                .replace("ó", "o")
                for col in df.columns
            ]

            # ============================
            # 🧹 Limpieza
            # ============================
            df["anio"] = anio

            # Limpiar total
            if "total" in df.columns:
                df["total"] = (
                    df["total"]
                    .str.replace(",", "", regex=False)
                    .fillna("0")
                    .astype(int)
                )

            # Limpiar grupo
            if "grupo" in df.columns:
                df["grupo"] = df["grupo"].str.strip()

            # Limpiar claves
            if "clues" in df.columns:
                df["clues"] = df["clues"].str.upper().str.strip()

            # ============================
            # 🏥 Filtrar por catálogo
            # ============================
            conn = mysql.connection
            cursor = conn.cursor()

            cursor.execute("SELECT clues FROM catalogo_unidades")
            claves_validas = set(row[0].upper().strip() for row in cursor.fetchall())

            df = df[df["clues"].isin(claves_validas)].copy()

            # ============================
            # 🔓 DB
            # ============================
            cursor.execute("SET FOREIGN_KEY_CHECKS = 0")

            if modo in ["actualizar", "reemplazar"]:
                cursor.execute("DELETE FROM afecciones_morbi WHERE anio = %s", (anio,))

            # ============================
            # 🚀 Insertar en bloques
            # ============================
            columnas_db = [
                "anio", "jurisdiccion", "municipio", "clues", "mes","especialidad",
                "grupo", "total"
            ]

            # Asegurar columnas
            for col in columnas_db:
                if col not in df.columns:
                    df[col] = None

            df_final = df[columnas_db]

            valores = [tuple(x) for x in df_final.to_numpy()]

            sql = f"""
                INSERT INTO afecciones_morbi ({', '.join(columnas_db)})
                VALUES ({', '.join(['%s'] * len(columnas_db))})
            """

            bloque = 10000
            for i in range(0, len(valores), bloque):
                cursor.executemany(sql, valores[i:i + bloque])

            conn.commit()

            flash(f"Afecciones {anio} cargado correctamente", "success")

        except Exception as e:
            conn.rollback()
            flash(f"Error: {str(e)}", "danger")
            print(f"❌ Error afecciones: {e}")

        finally:
            cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
            cursor.close()

        return redirect(url_for('admin.subir_csv_afecciones_morbi'))

    return render_template('admin/subir_csv_afecciones_morbi.html')



@admin.route('/upload_afecciones_morta', methods=['GET', 'POST'])
@login_required
def subir_csv_afecciones_morta():
    if request.method == 'POST':

        file = request.files.get("file")
        anio = request.form.get("anio")
        modo = request.form.get("modo_carga")

        if not file or not anio:
            flash("Falta archivo o año", "danger")
            return redirect(url_for('admin.subir_csv_afecciones_morta'))

        anio = int(anio)

        try:
            # ============================
            # 📖 Leer CSV
            # ============================
            df = pd.read_csv(file, dtype=str)

            # Normalizar columnas
            df.columns = [
                col.strip().lower()
                .replace(" ", "_")
                .replace("ó", "o")
                for col in df.columns
            ]

            # ============================
            # 🧹 Limpieza
            # ============================
            df["anio"] = anio

            # Limpiar total
            if "total" in df.columns:
                df["total"] = (
                    df["total"]
                    .str.replace(",", "", regex=False)
                    .fillna("0")
                    .astype(int)
                )

            # Limpiar grupo
            if "grupo" in df.columns:
                df["grupo"] = df["grupo"].str.strip()

            # Limpiar claves
            if "clues" in df.columns:
                df["clues"] = df["clues"].str.upper().str.strip()

            # ============================
            # 🏥 Filtrar por catálogo
            # ============================
            conn = mysql.connection
            cursor = conn.cursor()

            cursor.execute("SELECT clues FROM catalogo_unidades")
            claves_validas = set(row[0].upper().strip() for row in cursor.fetchall())

            df = df[df["clues"].isin(claves_validas)].copy()

            # ============================
            # 🔓 DB
            # ============================
            cursor.execute("SET FOREIGN_KEY_CHECKS = 0")

            if modo in ["actualizar", "reemplazar"]:
                cursor.execute("DELETE FROM afecciones_morta WHERE anio = %s", (anio,))

            # ============================
            # 🚀 Insertar en bloques
            # ============================
            columnas_db = [
                "anio", "jurisdiccion", "municipio", "clues", "mes","especialidad",
                "grupo", "total"
            ]

            # Asegurar columnas
            for col in columnas_db:
                if col not in df.columns:
                    df[col] = None

            df_final = df[columnas_db]

            valores = [tuple(x) for x in df_final.to_numpy()]

            sql = f"""
                INSERT INTO afecciones_morta ({', '.join(columnas_db)})
                VALUES ({', '.join(['%s'] * len(columnas_db))})
            """

            bloque = 10000
            for i in range(0, len(valores), bloque):
                cursor.executemany(sql, valores[i:i + bloque])

            conn.commit()

            flash(f"Afecciones {anio} cargado correctamente", "success")

        except Exception as e:
            conn.rollback()
            flash(f"Error: {str(e)}", "danger")
            print(f"❌ Error afecciones: {e}")

        finally:
            cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
            cursor.close()

        return redirect(url_for('admin.subir_csv_afecciones_morta'))

    return render_template('admin/subir_csv_afecciones_morta.html')
from datetime import timedelta

import pymysql
pymysql.install_as_MySQLdb()  # ⚡ IMPORTANTE: llamar la función
import MySQLdb
from flask import Flask
from flask_login import LoginManager
from flask_mysqldb import MySQL  # Necesario para la extensión de Flask
from flask_wtf.csrf import CSRFProtect
from config import Config

# Inicializar extensiones
csrf = CSRFProtect()
mysql = MySQL()
login_manager = LoginManager()


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.secret_key = Config.SECRET_KEY
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)  # Sesión expira después de 30 minutos de inactividad
    app.config['SESSION_PERMANENT'] = False  # La sesión no es permanente por defecto
    # Seguridad cookies
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['REMEMBER_COOKIE_DURATION'] = timedelta(seconds=0)
    
    # Tamaño máximo para cargas
    app.config['MAX_CONTENT_LENGTH'] = 250 * 1024 * 1024  # 250 MB

    # Inicializar extensiones
    mysql.init_app(app)
    login_manager.init_app(app)
    login_manager.session_protection = "strong"
    csrf.init_app(app)

        
    login_manager.login_view = 'main.login'

    # --------------------------------------
    # IMPORTAR Y REGISTRAR BLUEPRINTS
    # --------------------------------------
    #from app.routes.auth_routes import main as auth_bp
    from app.routes.admin_routes import admin as admin_bp
    from app.routes.egresos import egresos as egresos_bp
    from app.routes.reportes import reportes as reportes_bp
    from app.routes.urgencias import urgencias as urgencias_bp
    from app.routes.sis import sis as sis_bp
    from app.routes.indicador import indicador as indicador_bp
    from app.routes.grafica import grafica as grafica_bp
    from app.routes.main import main as main_bp
    from app.routes.agenda import agenda as agenda_bp
    from app.routes.bienvenida import bienvenida_bp as bienvenida_bd

    # Usuario anónimo
    from app.models import Anonymous
    login_manager.anonymous_user = Anonymous

    # Rutas principales
    #app.register_blueprint(auth_bp)  # login
    app.register_blueprint(admin_bp, url_prefix='/admin')
    #app.register_blueprint(usuarios_bp, url_prefix='/usuarios')

    # Módulos hospitalarios
    app.register_blueprint(bienvenida_bd)
    app.register_blueprint(egresos_bp)
    app.register_blueprint(reportes_bp)
    app.register_blueprint(urgencias_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(sis_bp)
    app.register_blueprint(indicador_bp)
    app.register_blueprint(grafica_bp)
    app.register_blueprint(agenda_bp)

    # --------------------------------------
    # MANEJO DE ERRORES
    # --------------------------------------
    @app.errorhandler(404)
    def page_not_found(e):
        return "Página no encontrada", 404

    @app.errorhandler(500)
    def internal_server_error(e):
        return "Error interno del servidor", 500

    # --------------------------------------
    # CARGA DE USUARIO (Flask-Login)
    # --------------------------------------
    @login_manager.user_loader
    def load_user(user_id):
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute("SELECT * FROM user WHERE id = %s", (user_id,))
        user_data = cursor.fetchone()
        cursor.close()

        from app.models import User
        if user_data:
            return User(
                id=user_data['id'],
                nombre=user_data['nombre'],
                primer_apellido=user_data['primer_apellido'],
                segundo_apellido=user_data['segundo_apellido'],
                sexo=user_data['sexo'],
                rfc=user_data['rfc'],
                email=user_data['email'],
                username=user_data['username'],
                password=user_data['password'],
                fecha_registro=user_data['fecha_registro'],
                rol_id=user_data['rol_id'],
                nombre_oculto=user_data.get('nombre_oculto', '')
            )
        return None

    return app



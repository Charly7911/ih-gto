from flask_login import UserMixin, AnonymousUserMixin
from werkzeug.security import check_password_hash
from datetime import datetime


class User(UserMixin):
    def __init__(self, id, nombre, primer_apellido, segundo_apellido,sexo, rfc, email, username, password, fecha_registro, rol_id, nombre_oculto):
        self.id = id
        self.nombre = nombre
        self.primer_apellido = primer_apellido
        self.segundo_apellido = segundo_apellido
        self.sexo = sexo
        self.rfc = rfc
        self.email = email
        self.username = username
        self.password = password
        self.fecha_registro = fecha_registro
        self.rol_id = rol_id
        self.nombre_oculto = nombre_oculto

    def get_id(self):
        return str(self.id)

    def is_active(self):
        return True

    def is_authenticated(self):
        return True

    def is_anonymous(self):
        return False

    def check_password(self, password):
        return check_password_hash(self.password.strip(), password)
    
import mysql.connector
from config import Config

def get_db_connection():
    config = Config()
    return mysql.connector.connect(
        host=config.MYSQL_HOST,
        user=config.MYSQL_USER,
        password=config.MYSQL_PASSWORD,
        database=config.MYSQL_DB,
        charset='utf8mb4'
    )



class Anonymous(AnonymousUserMixin):
    @property
    def rol_id(self):
        return 2  # rol usuario normal

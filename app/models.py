from flask_login import UserMixin, AnonymousUserMixin
from werkzeug.security import check_password_hash
import mysql.connector
from config import Config

class User(UserMixin):
    def __init__(self, id, nombre, primer_apellido, segundo_apellido, sexo, rfc, email, username, password, fecha_registro, rol_id, nombre_oculto):
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

    def check_password(self, password):
        return check_password_hash(self.password, password)


class Anonymous(AnonymousUserMixin):
    @property
    def rol_id(self):
        return 2  # rol usuario normal por defecto


def get_db_connection():
    config = Config()
    return mysql.connector.connect(
        host=config.MYSQL_HOST,
        user=config.MYSQL_USER,
        password=config.MYSQL_PASSWORD,
        database=config.MYSQL_DB,
        charset='utf8mb4'
    )

# 🟢 Función imprescindible para que current_user mantenga nombre y apellido entre paginas
def load_user_by_id(user_id, mysql_obj):
    cursor = mysql_obj.connection.cursor(MySQLdb.cursors.DictCursor)
    try:
        cursor.execute("SELECT * FROM user WHERE id = %s", (user_id,))
        u = cursor.fetchone()
        if u:
            return User(
                id=u['id'],
                nombre=u['nombre'],
                primer_apellido=u['primer_apellido'],
                segundo_apellido=u['segundo_apellido'],
                sexo=u['sexo'],
                rfc=u['rfc'],
                email=u['email'],
                username=u['username'],
                password=u['password'],
                fecha_registro=u['fecha_registro'],
                rol_id=u['rol_id'],
                nombre_oculto=u['nombre_oculto']
            )
        return None
    finally:
        cursor.close()

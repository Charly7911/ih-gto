import os

class Config:
    SECRET_KEY = '*(Chichin)$'
    if 'PYTHONANYWHERE_DOMAIN' in os.environ:
        MYSQL_HOST = 'Charly7911.mysql.pythonanywhere-services.com'
        MYSQL_USER = 'Charly7911'
        MYSQL_PASSWORD = '$Estadistic4#'
        MYSQL_DB = 'Charly7911$indicador_hospitalario'
    else:
        MYSQL_HOST = 'localhost'
        MYSQL_USER = 'oficios_dgp'
        MYSQL_PASSWORD = '$Estadistic4#'
        MYSQL_DB = 'indicador_hospitalario'
    
    

    @property
    def DB_URI(self):
        return (
            f"mysql+pymysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}"
            f"@{self.MYSQL_HOST}/{self.MYSQL_DB}"
        )
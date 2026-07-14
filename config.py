class Config:
    SECRET_KEY = '*(Chichin)$'
    MYSQL_USER = 'oficios_dgp'
    MYSQL_PASSWORD = '$Estadistic4#'
    MYSQL_HOST = 'localhost'
    MYSQL_DB = 'indicador_hospitalario'
    
    

    @property
    def DB_URI(self):
        return (
            f"mysql+pymysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}"
            f"@{self.MYSQL_HOST}/{self.MYSQL_DB}"
        )
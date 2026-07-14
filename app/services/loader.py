import importlib

def cargar_indicador(sistema, nombre):
    module_path = f"app.indicators.{sistema}.{nombre}"
    module = importlib.import_module(module_path)
    return module

from flask import Blueprint, render_template
from flask import Blueprint, render_template


bienvenida_bp = Blueprint('bienvenida', __name__)

@bienvenida_bp.route('/')
def inicio():
    # Asegúrate de que la ruta al archivo sea correcta según tu carpeta templates
    return render_template('bienvenida/bienvenida.html')
import os
from flask import Blueprint, jsonify, render_template, current_app
from flask_login import login_required

agenda = Blueprint('agenda', __name__, url_prefix='/agenda')

@agenda.route('/visor')
@login_required
def visor():
    return render_template('agendas/agenda.html')


# En tu archivo de rutas (ej: routes/agenda_routes.py)

@agenda.route('/api/lista-paginas')
@login_required
def lista_paginas():
    # CAMBIO: Ahora buscamos en la carpeta de imágenes
    ruta_imagenes = os.path.join(current_app.root_path, 'static', 'img', 'agenda')
    
    if not os.path.exists(ruta_imagenes):
        return jsonify({"paginas": []})
        
    # Listamos y ordenamos archivos .jpg
    archivos = sorted([f for f in os.listdir(ruta_imagenes) if f.lower().endswith('.webp')])
    return jsonify({"paginas": archivos})
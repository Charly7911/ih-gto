import os
from flask import Blueprint, jsonify, render_template, current_app

agenda = Blueprint('agenda', __name__, url_prefix='/agenda')

@agenda.route('/visor')
def visor():
    return render_template('agendas/agenda.html')


# En tu archivo de rutas (ej: routes/agenda_routes.py)

@agenda.route('/api/lista-paginas')
def lista_paginas():
    # CAMBIO: Ahora buscamos en la carpeta de imágenes
    ruta_imagenes = os.path.join(current_app.root_path, 'static', 'img', 'agenda')
    
    if not os.path.exists(ruta_imagenes):
        return jsonify({"paginas": []})
        
    # Listamos y ordenamos archivos .jpg
    archivos = sorted([f for f in os.listdir(ruta_imagenes) if f.lower().endswith('.webp')])
    return jsonify({"paginas": archivos})
from flask import Blueprint, render_template
from app.routes.forms import LoginForm
from flask_login import current_user


bienvenida_bp = Blueprint('bienvenida', __name__)


@bienvenida_bp.route('/')
def inicio():

    form = LoginForm()
    print("USUARIO ACTUAL:", current_user)
    print("ESTA AUTENTICADO:", current_user.is_authenticated)

    return render_template(
        'bienvenida/bienvenida.html',
        form=form,
        mostrar_login=not current_user.is_authenticated
    )
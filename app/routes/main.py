# app/routes/main.py
import traceback
import MySQLdb
from flask import Blueprint, current_app, flash, render_template, redirect, request, session, url_for
from flask_login import login_required, login_user, current_user, logout_user
from app import mysql
from app.models import User
from app.routes.forms import LoginForm

main = Blueprint('main', __name__)



# -----------------------------
# LOGIN SOLO PARA ADMIN
# -----------------------------


@main.route('/login', methods=['GET', 'POST'])
def login():

    if current_user.is_authenticated:
        return redirect(url_for('bienvenida.inicio'))

    form = LoginForm()

    if form.validate_on_submit():

        username = form.username.data
        password = form.password.data

        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

        try:
            cursor.execute(
                'SELECT * FROM user WHERE username = %s',
                (username,)
            )

            user_data = cursor.fetchone()

            if not user_data:
                flash('Usuario no encontrado.', 'danger')
                return render_template(
                    'bienvenida/bienvenida.html',
                    form=form, mostrar_login=True
                )


            user = User(
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
                nombre_oculto=user_data['nombre_oculto']
            )


            if not user.check_password(password):

                flash('Contraseña incorrecta.', 'danger')

                return render_template(
                    'bienvenida/bienvenida.html',
                    form=form, mostrar_login=True
                )


            login_user(user, remember=False)

            session['user_id'] = user.id
            session['user_rol'] = user.rol_id

            current_app.logger.info(
                f"LOGIN OK: {current_user.username} - autenticado: {current_user.is_authenticated}"
            )


            # Administrador
            if user.rol_id == 6:
                return redirect(
                    url_for('bienvenida.inicio')
                )


            # Usuario normal
            if user.rol_id == 1:
                return redirect(
                    url_for('bienvenida.inicio')
                )


            return redirect(
                url_for('bienvenida.inicio')
            )


        except Exception as e:

            current_app.logger.error(e)

            flash(
                'Error interno del servidor.',
                'danger'
            )


        finally:
            cursor.close()


    return render_template(
        'bienvenida/bienvenida.html',
        form=form, mostrar_login=True
    )



@main.route('/logout')
@login_required
def logout():

    logout_user()
    session.clear()

    flash(
        "Sesión cerrada correctamente.",
        "success"
    )

    return redirect(url_for('bienvenida.inicio'))


@main.route('/acceso-admin')
def acceso_admin():
    return render_template('login.html')





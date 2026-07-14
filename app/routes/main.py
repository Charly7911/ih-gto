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
        return redirect(url_for('egresos.indicadores_page', home=1))

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
                return render_template('login.html', form=form)

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
                return render_template('login.html', form=form)

            login_user(user)

            session['user_id'] = user.id
            session['user_rol'] = user.rol_id

            if user.rol_id == 6:
                return redirect(url_for('admin.dashboard', home=1))

            if user.rol_id == 1:
                return redirect(url_for('usuarios.dashboard', home=1))

            return redirect(url_for('egresos.indicadores_page', home=1))

        except Exception as e:
            current_app.logger.error(e)
            flash('Error interno del servidor.', 'danger')

        finally:
            cursor.close()

    return render_template('login.html', form=form)



@main.route('/logout')
@login_required
def logout():
    logout_user()  # Cierra sesión en Flask-Login
    session.clear()  # Limpia variables de sesión
    flash("Sesión cerrada correctamente.", "success")
    return redirect(url_for('main.login'))


@main.route('/acceso-admin')
def acceso_admin():
    return render_template('login.html')





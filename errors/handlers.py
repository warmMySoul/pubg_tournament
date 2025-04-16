from flask import Blueprint, render_template

errors = Blueprint('errors', __name__)

@errors.app_errorhandler(Exception)
def handle_error(error):
    # Импорт здесь, чтобы избежать циклических импортов
    from werkzeug.exceptions import HTTPException

    if isinstance(error, HTTPException):
        code = error.code
        return render_template('errors/error.html', code=code), code

    # Фолбэк — неизвестная ошибка
    return render_template('errors/error.html', code=500), 500

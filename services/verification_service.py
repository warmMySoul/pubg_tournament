import secrets
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from flask import current_app
from flask_mail import Message
from extensions.mail_connect import mail

def generate_verification_code(length=6):
    """Генерирует случайный цифровой код."""
    return ''.join(secrets.choice('0123456789') for _ in range(length))

def send_verification_email(email, code):
    """Отправляет код подтверждения на email."""
    msg = Message(
        subject="Код подтверждения",
        sender=current_app.config['MAIL_USERNAME'],
        recipients=[email],
        body=f"Ваш код подтверждения: {code} (действует 5 минут)"
    )
    mail.send(msg)

def is_code_valid(saved_code, saved_expiry, entered_code):
    """Проверяет, совпадает ли код и не истек ли срок."""
    if not saved_code or not saved_expiry:
        return False
    return (saved_code == entered_code) and (datetime.now(ZoneInfo("Europe/Moscow")) <= saved_expiry)
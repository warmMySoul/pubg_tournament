from datetime import datetime

# Проверка доступности регистрации
def registration_open(tournament):
    now = datetime.now()
    return tournament.reg_start <= now <= tournament.reg_end
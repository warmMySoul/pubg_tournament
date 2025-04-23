from datetime import datetime

# Проверка доступности регистрации
def registration_open(tournament):
    now = datetime.now()
    return tournament.reg_start <= now <= tournament.reg_end

# Максировка email
def mask_email(email):
    if not email or '@' not in email:
        return email
        
    username, domain = email.split('@', 1)
    if len(username) <= 3:
        masked = '*' * len(username)
    else:
        masked = username[:3] + '*' * (len(username) - 3)
    
    return f"{masked}@{domain}"
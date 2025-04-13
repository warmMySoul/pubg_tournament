from datetime import datetime
from db_connection import db

class RoleEnum:
    ADMIN = 'admin'
    MODERATOR = 'moderator'
    CLAN_MEMBER = 'clan_member'
    GUEST = 'guest'

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    discord_id = db.Column(db.String(50), unique=True, nullable=True)
    name = db.Column(db.String(70), nullable=True)
    pubg_nickname = db.Column(db.String(70), unique=True, nullable=False)
    birthday = db.Column(db.DateTime, nullable=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), default=RoleEnum.GUEST)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def check_password(self, password):
        from werkzeug.security import check_password_hash
        return check_password_hash(self.password, password)

    def set_password(self, password):
        from werkzeug.security import generate_password_hash
        self.password = generate_password_hash(password)

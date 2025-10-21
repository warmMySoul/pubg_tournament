from datetime import datetime
from zoneinfo import ZoneInfo
from extensions.db_connection import db

class RqStatusEnum():
    REVIEW = 'На рассмотрении'
    ACCEPTED = 'Принята'
    DECLINED = 'Отклонена'

    def __str__(self):
        return self.value

class JoinRequests(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    user_info = db.Column(db.String(480))
    know_from = db.Column(db.String(100))
    desired_role = db.Column(db.Boolean, nullable=False)
    status = db.Column(db.String(32), nullable=False)
    reason = db.Column(db.String(256))
    moderator_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    moderate_at = db.Column(db.DateTime, default=lambda: datetime.now(ZoneInfo("Europe/Moscow")))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(ZoneInfo("Europe/Moscow")))
    
    user = db.relationship(
        'User', 
        foreign_keys=[user_id],
        backref=db.backref('join_requests', cascade='all, delete-orphan'),
        lazy=True,
        single_parent=True
    )
    
    moderator = db.relationship(
        'User', 
        foreign_keys=[moderator_id],
        lazy=True
    )

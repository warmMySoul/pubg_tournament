import importlib
from flask_apscheduler import APScheduler
from models import ScheduledTask
from extensions.db_connection import db
from pubg_api.tasks import *
from flask import current_app

scheduler = APScheduler()

def init_scheduler(app):
    scheduler.init_app(app)
    
    # Загружаем активные задачи из БД при старте
    with app.app_context():
        if not scheduler.running:
            scheduler.start()
        tasks = ScheduledTask.query.filter_by(is_active=True).all()
        for task in tasks:
            add_periodic_task(task,app)

def get_task_function(function_name):
    module = importlib.import_module(f'pubg_api.tasks.{function_name}')
    return getattr(module, function_name)

def add_periodic_task(task, app):
    job_id = str(task.id)

    # Удаляем старую, если есть
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)

    func = get_task_function(task.function_name)

    scheduler.add_job(
        id=job_id,
        args=[app],
        func=func,
        trigger='interval',
        minutes=task.interval_minutes,
        replace_existing=True
    )

def remove_periodic_task(task):
    job_id = str(task.id)
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)

def toggle_task(task, activate: bool, app):
    task.is_active = activate
    db.session.commit()

    if activate:
        add_periodic_task(task, app)
    else:
        remove_periodic_task(task)

def run_task_now(task,app):
    func = get_task_function(task.function_name)
    with app.app_context():
        func(app)
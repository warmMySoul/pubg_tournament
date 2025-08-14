# services/queue_service.py
import pika
import json
from functools import wraps

class QueueService:
    _connection = None
    
    @classmethod
    def get_channel(cls):
        if cls._connection is None or cls._connection.is_closed:
            cls._connection = pika.BlockingConnection(
                pika.ConnectionParameters('localhost')
            )
        return cls._connection.channel()
    
    @classmethod
    def publish_task(cls, task_data, queue_name='pubg_tasks'):
        try:
            channel = cls.get_channel()
            channel.basic_publish(
                exchange='',
                routing_key=queue_name,
                body=json.dumps(task_data),
                properties=pika.BasicProperties(
                    delivery_mode=2  # Сохраняем задачи
                )
            )
            return True
        except Exception as e:
            print(f"Queue publish error: {e}")
            return False

def queue_task(queue_name='pubg_tasks'):
    """Декоратор для добавления задачи в очередь после выполнения функции"""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            result = f(*args, **kwargs)
            if result and isinstance(result, tuple) and len(result) == 2:
                response, task_data = result
                QueueService.publish_task(task_data, queue_name)
                return response
            return result
        return wrapper
    return decorator
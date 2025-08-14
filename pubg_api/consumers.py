import os
import sys
import time
import pika
import json
import threading
from client import PUBGApiClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

class PUBGConsumer:
    def __init__(self, api_key: str):
        self.client = PUBGApiClient(api_key)
        if not hasattr(self, 'engine'):
            self.engine = create_engine('sqlite:///instance/tournament.db')
            self.Session = sessionmaker(bind=self.engine)
    
    def process_task(self, ch, method, properties, body):
        session = self.Session()  # Для решения 2
        try:
            task = json.loads(body)
            print(f"[→] Выполнение задачи: {task}")

            if task["type"] == "get_player":
                result = self.client.get_player_by_name(task["player_name"])
            elif task["type"] == "get_lifetime_stats":
                result = self.client.get_player_lifetime_stats_by_id(task["player_id"])
            elif task["type"] == "get_match":
                result = self.client.get_match_by_id(task["match_id"])
            else:
                raise ValueError("Unknown task type")

            print(f"[✓] Задача {task["type"]} выполнена: {result}")
            ch.basic_ack(delivery_tag=method.delivery_tag)

        except Exception as e:
            print(f"[!] Ошибка: {e}")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        finally:
            session.close()

def start_consumer(api_key: str):
    connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
    channel = connection.channel()
    channel.queue_declare(queue='pubg_tasks', durable=True)
    channel.basic_qos(prefetch_count=1)  # По 1 задаче за раз

    consumer = PUBGConsumer(api_key)
    channel.basic_consume(queue='pubg_tasks', on_message_callback=consumer.process_task)
    
    print(f"[*] Consumer with key {api_key[-4:]}... started")
    channel.start_consuming()

# Запуск консьюмеров
if __name__ == '__main__':
    try:
        load_dotenv("secrets.env")

        api_keys = [
            os.getenv("PUBG_API_KEY_1"),  # Разные токены для каждого консьюмера (для расширения добавить)
            os.getenv("PUBG_API_KEY_2")
        ]

        for key in api_keys:
            if not key:
                continue
            threading.Thread(
                target=start_consumer,
                args=(key,),
                daemon=True
            ).start()
        
        # Бесконечное ожидание
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down consumers...")
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)
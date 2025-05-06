# pubg_api/queue_worker.py
import itertools
import threading
import queue
import time
from datetime import datetime

class APIQueueWorker(threading.Thread):
    def __init__(self, client, rate_limit=10, max_queue_size=50):
        super().__init__(daemon=True)
        self.client = client
        self.rate_limit = rate_limit
        self.max_queue_size = max_queue_size
        self.task_queue = queue.PriorityQueue(maxsize=max_queue_size)
        self.last_requests = []
        self.counter = itertools.count()

    def run(self):
        while True:
            try:
                priority, count, task_data = self.task_queue.get()
                func, args, kwargs, result_queue = task_data

                print(f"[WORKER] Выполняю задачу: {func.__name__} с args={args} kwargs={kwargs}")

                self._enforce_rate_limit()

                try:
                    app = args[0]  # Берём app из переданных аргументов
                    with app.app_context():
                        print(f"[WORKER] Запускаю функцию {func.__name__}")
                        result = func(*args, **kwargs)
                        print(f"[WORKER] функция {result}")
                        print(f"[WORKER] Задача {func.__name__} выполнена успешно")
                        result_queue.put((result, None))
                except Exception as e:
                    print(f"[WORKER] Ошибка в задаче {func.__name__}: {e}")
                    result_queue.put((None, e))

                self.task_queue.task_done()

            except Exception as e:
                print(f"Ошибка в worker: {e}")

    def _enforce_rate_limit(self):
        now = datetime.now()
        self.last_requests = [
            ts for ts in self.last_requests if (now - ts).total_seconds() < 60
        ]

        if len(self.last_requests) >= self.rate_limit:
            earliest = self.last_requests[0]
            sleep_time = 60 - (now - earliest).total_seconds()
            time.sleep(max(sleep_time, 0))

        self.last_requests.append(datetime.now())

    def add_task(self, func, *args, priority=1, **kwargs):
        result_queue = queue.Queue()
        count = next(self.counter)
        task_data = (func, args, kwargs, result_queue)
        self.task_queue.put((priority, count, task_data))
        return result_queue

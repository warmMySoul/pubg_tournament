# pubg_tournament
Этот репозиторий содержит инструменты для организации и проведения турниров по PlayerUnknown's Battlegrounds (PUBG).
Так же возможны учет и управление участников клана.

## 📌 О проекте
Проект предоставляет удобный способ управления турнирами, включая:

- Регистрацию участников
- Формирование лобби и расписания матчей
- Подсчёт очков и ведение статистики
- Генерацию отчётов и таблиц результатов

## 🛠 Локальный запуск проекта

1. Клонирование репозитория:
	```bash
	git clone https://github.com/warmMySoul/pubg_tournament.git
	cd pubg_tournament
	```
2. Создание виртуального окружения:
	```bash
	python -m venv venv
	```
3. Вход в окружение:
	1. __Windows__
		```bash
		.\venv\Scripts\activate
		```
	2. __Linux/MacOS__
		```bash
		source venv/bin/activate
		```
3. Установка зависимостей:
	```bash
	pip install -r requirements.txt
	```
4. Установка переменных окружения в _secrets.env_:
	```bash
	ADMIN_MAIL=<admin_mail>		# логин суперюзера
	ADMIN_PASS=<admin_pass>		# пароль суперюзера
	FERNET_KEY=<fernet_key>		# ключ шифрования
	MAIL_LOGIN=<mail_login>		# логин от почты mail.ru для рассылок
	PASSWORD=<password>		# пароль от учетки сервера, на котором запускаете проект
	PUBG_API_KEY=<pubg_api_key>	# ключ к [API](https://documentation.pubg.com/en/api-keys.html)
	SECRET_KEY=<secret_key>		# ключ для запуска проекта 
	USERNAME=<username> 		# логин от учетки сервера, на котором запускаете проект
	```
5. Запуск преокта:
	```bash
	python app.py
	```

## 📜 Лицензия
Этот проект распространяется под лицензией [MIT License](./LICENSE).

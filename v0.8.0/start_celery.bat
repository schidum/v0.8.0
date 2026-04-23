@echo off
echo Запуск Celery Worker (RabbitMQ)...
celery -A app.celery_app worker --loglevel=info --pool=solo
pause
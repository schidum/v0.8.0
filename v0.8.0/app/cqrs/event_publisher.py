# app/cqrs/event_publisher.py
from celery import shared_task
import json
from datetime import datetime
import uuid

from app.cqrs.events import DomainEvent


@shared_task
def publish_domain_event(event: dict):
    """Публикует доменное событие в очередь (Celery + RabbitMQ)"""
    print(f"📤 Опубликовано событие: {event['event_type']} | ID: {event.get('event_id')}")
    # Здесь можно добавить логику отправки в RabbitMQ напрямую, но через Celery проще
    return event
# app/cqrs/handlers/person_handler.py
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.cqrs.commands.person_commands import CreatePersonCommand, UpdatePersonCommand
from app.models import Person
from app.repositories import PersonRepository
from app.services import AuthService


class PersonCommandHandler:
    """Обработчик команд для пользователей (Command Side)"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = PersonRepository(db)

    async def create_person(self, cmd: CreatePersonCommand) -> Person:
        """Создание нового пользователя"""
        # Проверка уникальности логина
        existing = await self.repo.get_by_login(cmd.login)
        if existing:
            raise ValueError(f"Логин '{cmd.login}' уже существует")

        print(f"🔑 Хэшируем пароль для пользователя {cmd.login}")   # отладка

        person = Person(
            full_name=cmd.full_name,
            login=cmd.login,
            password_hash=AuthService.hash_password(cmd.password),   # ← важно!
            phone=cmd.phone,
            qualification=cmd.qualification,
            is_active=True,
        )

        person = await self.repo.create(person)
        await self.repo.set_roles(person, cmd.roles)

        print(f"✅ Пользователь {cmd.login} успешно создан (ID={person.id})")
        
        # Перезагружаем с ролями
        return await self.repo.get_by_id(person.id)

    async def update_person(self, cmd: UpdatePersonCommand) -> Optional[Person]:
        """Обновление пользователя"""
        person = await self.repo.get_by_id(cmd.person_id)
        if not person:
            return None

        if cmd.full_name is not None:
            person.full_name = cmd.full_name
        if cmd.phone is not None:
            person.phone = cmd.phone
        if cmd.qualification is not None:
            person.qualification = cmd.qualification
        if cmd.is_active is not None:
            person.is_active = cmd.is_active
        if cmd.roles is not None:
            await self.repo.set_roles(person, cmd.roles)

        return await self.repo.update(person)
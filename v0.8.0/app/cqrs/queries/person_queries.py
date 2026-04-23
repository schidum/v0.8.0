# app/cqrs/queries/person_queries.py
from typing import List, Optional
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.cqrs.dto.person_dto import PersonReadDTO


class PersonQuery:
    """Query side — чтение данных без ORM (совместимо с SQLite Python 3.8)"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_all(self) -> List[PersonReadDTO]:
        """Получить список всех пользователей"""
        query = text("""
            SELECT 
                p.id, 
                p.full_name, 
                p.login, 
                p.phone, 
                p.qualification, 
                p.is_active,
                COALESCE((
                    SELECT group_concat('"' || role || '"')
                    FROM person_roles pr 
                    WHERE pr.person_id = p.id
                ), '[]') as roles_str
            FROM persons p
            ORDER BY p.id
        """)
        result = await self.db.execute(query)
        rows = result.all()

        import json
        users = []
        for row in rows:
            # Преобразуем group_concat обратно в список
            roles_str = row.roles_str or "[]"
            try:
                roles = json.loads("[" + roles_str + "]") if roles_str != "[]" else []
            except:
                roles = []

            users.append(PersonReadDTO(
                id=row.id,
                full_name=row.full_name,
                login=row.login,
                phone=row.phone,
                qualification=row.qualification,
                is_active=row.is_active,
                roles=roles
            ))
        return users

    async def get_by_id(self, person_id: int) -> Optional[PersonReadDTO]:
        """Получить одного пользователя по ID"""
        query = text("""
            SELECT 
                p.id, 
                p.full_name, 
                p.login, 
                p.phone, 
                p.qualification, 
                p.is_active,
                COALESCE((
                    SELECT group_concat('"' || role || '"')
                    FROM person_roles pr 
                    WHERE pr.person_id = p.id
                ), '[]') as roles_str
            FROM persons p
            WHERE p.id = :person_id
        """)
        result = await self.db.execute(query, {"person_id": person_id})
        row = result.first()
        if not row:
            return None

        import json
        roles_str = row.roles_str or "[]"
        try:
            roles = json.loads("[" + roles_str + "]") if roles_str != "[]" else []
        except:
            roles = []

        return PersonReadDTO(
            id=row.id,
            full_name=row.full_name,
            login=row.login,
            phone=row.phone,
            qualification=row.qualification,
            is_active=row.is_active,
            roles=roles
        )
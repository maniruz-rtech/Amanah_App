"""
Base repository with common CRUD operations.
"""

from typing import Any, Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """Base repository with common CRUD operations."""

    def __init__(self, model: type[ModelType], db: AsyncSession):
        self.model = model
        self.db = db

    async def get_by_id(self, id: str) -> ModelType | None:
        """Get entity by ID."""
        result = await self.db.execute(
            select(self.model).where(self.model.id == id)
        )
        return result.scalar_one_or_none()

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        **filters: Any,
    ) -> list[ModelType]:
        """Get all entities with optional filtering."""
        query = select(self.model)

        for field, value in filters.items():
            if value is not None and hasattr(self.model, field):
                query = query.where(getattr(self.model, field) == value)

        query = query.offset(skip).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def create(self, **data: Any) -> ModelType:
        """Create a new entity."""
        instance = self.model(**data)
        self.db.add(instance)
        await self.db.flush()
        await self.db.refresh(instance)
        return instance

    async def update(self, id: str, **data: Any) -> ModelType | None:
        """Update an entity by ID."""
        instance = await self.get_by_id(id)
        if instance is None:
            return None

        for field, value in data.items():
            if value is not None and hasattr(instance, field):
                setattr(instance, field, value)

        await self.db.flush()
        await self.db.refresh(instance)
        return instance

    async def delete(self, id: str) -> bool:
        """Delete an entity by ID."""
        instance = await self.get_by_id(id)
        if instance is None:
            return False

        await self.db.delete(instance)
        await self.db.flush()
        return True

    async def exists(self, **filters: Any) -> bool:
        """Check if entity exists with given filters."""
        query = select(self.model.id)

        for field, value in filters.items():
            if value is not None and hasattr(self.model, field):
                query = query.where(getattr(self.model, field) == value)

        result = await self.db.execute(query.limit(1))
        return result.scalar_one_or_none() is not None

    async def count(self, **filters: Any) -> int:
        """Count entities with optional filtering."""
        from sqlalchemy import func

        query = select(func.count(self.model.id))

        for field, value in filters.items():
            if value is not None and hasattr(self.model, field):
                query = query.where(getattr(self.model, field) == value)

        result = await self.db.execute(query)
        return result.scalar() or 0

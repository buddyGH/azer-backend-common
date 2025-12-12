# azer_common/repositories/base_component.py
from typing import Optional, List, Dict, Any, Tuple


class BaseComponent:
    """组件基类 - 提供基础功能和常用方法代理"""

    def __init__(self, repository):
        self.repository = repository
        self.model = repository.model
        self.soft_delete_field = repository.soft_delete_field

    @property
    def query(self):
        """获取基础查询"""
        return self.repository.get_query()

    # ========== 基础查询方法 ==========
    async def get_by_field(self, field: str, value: Any) -> Optional[Any]:
        """根据字段值获取记录"""
        return await self.query.filter(**{field: value}).first()

    async def get_by_fields(self, **filters) -> Optional[Any]:
        """根据多个字段值获取记录"""
        return await self.query.filter(**filters).first()

    async def exists_by_field(self, field: str, value: Any) -> bool:
        """判断字段值是否存在"""
        return await self.query.filter(**{field: value}).exists()

    # ========== 代理常用Repository方法 ==========
    async def get_by_id(self, id: str) -> Optional[Any]:
        return await self.repository.get_by_id(id)

    async def create(self, **data) -> Any:
        return await self.repository.create(**data)

    async def update(self, id: str, **data) -> Optional[Any]:
        return await self.repository.update(id, **data)

    async def delete(self, id: str, soft: bool = True) -> bool:
        return await self.repository.delete(id, soft)

    async def count(self, **filters) -> int:
        return await self.repository.count(**filters)

    # ========== 便捷方法 ==========
    async def get_or_none(self, **filters) -> Optional[Any]:
        """获取或返回None"""
        return await self.query.filter(**filters).first()

    async def get_all(self, **filters) -> List[Any]:
        """获取所有记录"""
        return await self.query.filter(**filters).all()

    async def create_if_not_exists(
            self, identifier_field: str,
            identifier_value: Any, **data) -> Tuple[Any, bool]:
        """如果不存在则创建"""
        exists = await self.exists_by_field(identifier_field, identifier_value)
        if exists:
            instance = await self.get_by_field(identifier_field, identifier_value)
            return instance, False
        else:
            data[identifier_field] = identifier_value
            instance = await self.create(**data)
            return instance, True

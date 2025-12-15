# azer_common/repositories/base_component.py
from typing import Optional, List, Dict, Any, Tuple, TypeVar, Generic
from contextlib import asynccontextmanager

T = TypeVar("T")


class BaseComponent(Generic[T]):
    """组件基类 - 提供基础功能和常用方法代理"""

    def __init__(self, repository):
        self.repository = repository
        self.model = repository.model
        self.soft_delete_field = repository.soft_delete_field

    @property
    def query(self):
        """获取基础查询"""
        return self.repository.get_query()

    # ========== 事务管理 ==========

    @asynccontextmanager
    async def transaction(self):
        """获取事务上下文"""
        async with self.repository.transaction() as transaction:
            yield transaction

    # ========== 基础查询方法 ==========

    async def get_by_field(self, field: str, value: Any) -> Optional[T]:
        """根据字段值获取记录"""
        return await self.query.filter(**{field: value}).first()

    async def get_by_fields(self, **filters) -> Optional[T]:
        """根据多个字段值获取记录"""
        return await self.query.filter(**filters).first()

    async def exists_by_field(self, field: str, value: Any) -> bool:
        """判断字段值是否存在"""
        return await self.query.filter(**{field: value}).exists()

    # ========== 代理常用Repository方法 ==========

    async def get_by_id(self, id: str) -> Optional[T]:
        return await self.repository.get_by_id(id)

    async def get_by_ids(self, ids: List[str]) -> List[T]:
        return await self.repository.get_by_ids(ids)

    async def create(self, **data) -> T:
        return await self.repository.create(**data)

    async def update(self, id: str, **data) -> Optional[T]:
        return await self.repository.update(id, **data)

    async def delete(self, id: str, soft: bool = True) -> bool:
        return await self.repository.delete(id, soft)

    async def count(self, **filters) -> int:
        return await self.repository.count(**filters)

    # ========== 批量操作代理 ==========

    async def bulk_create(self, data_list: List[Dict[str, Any]]) -> List[T]:
        """批量创建记录（带事务）"""
        return await self.repository.bulk_create(data_list)

    async def bulk_update(self, ids: List[str], **data) -> int:
        """批量更新记录（带事务）"""
        return await self.repository.bulk_update(ids, **data)

    async def bulk_delete(self, ids: List[str], soft: bool = True) -> int:
        """批量删除记录（带事务）"""
        return await self.repository.bulk_delete(ids, soft)

    async def enhanced_bulk_update(
        self,
        ids: List[str],
        update_data: Dict[str, Any],
        before_update_callback: Optional[callable] = None,
        after_update_callback: Optional[callable] = None,
        **kwargs,
    ) -> Tuple[int, List[T]]:
        """增强型批量更新（支持前后回调）"""
        return await self.repository.enhanced_bulk_update(
            ids, update_data, before_update_callback, after_update_callback, **kwargs
        )

    # ========== 查询代理 ==========

    async def filter(
        self, offset: int = 0, limit: int = 20, order_by: Optional[str] = None, **filters
    ) -> Tuple[List[T], int]:
        return await self.repository.filter(offset, limit, order_by, **filters)

    async def search(self, keyword: str = None, search_fields: List[str] = None, **filters) -> Tuple[List[T], int]:
        return await self.repository.search(keyword, search_fields, **filters)

    async def get_or_create(self, defaults: Dict[str, Any] = None, **kwargs) -> Tuple[T, bool]:
        return await self.repository.get_or_create(defaults, **kwargs)

    async def update_or_create(self, defaults: Dict[str, Any] = None, **kwargs) -> Tuple[T, bool]:
        return await self.repository.update_or_create(defaults, **kwargs)

    async def exists(self, **filters) -> bool:
        return await self.repository.exists(**filters)

    async def distinct_values(self, field: str, **filters) -> List[Any]:
        return await self.repository.distinct_values(field, **filters)

    # ========== 便捷方法 ==========

    async def get_or_none(self, **filters) -> Optional[T]:
        """获取或返回None"""
        return await self.query.filter(**filters).first()

    async def get_all(self, **filters) -> List[T]:
        """获取所有记录"""
        return await self.query.filter(**filters).all()

    # ========== 扩展方法 ==========

    async def bulk_restore(self, ids: List[str]) -> int:
        """批量恢复软删除的记录"""
        if not hasattr(self.model, self.soft_delete_field) or not ids:
            return 0

        async with self.transaction(self):
            update_data = {self.soft_delete_field: False, "deleted_at": None}

            query = self.model.filter(id__in=ids, **{self.soft_delete_field: True})

            result = await query.update(**update_data)
            return result if isinstance(result, int) else 0

    async def get_or_create_by_field(self, field: str, value: Any, defaults: Dict[str, Any] = None) -> Tuple[T, bool]:
        """根据字段值获取或创建记录"""
        if defaults is None:
            defaults = {}

        return await self.get_or_create(**{field: value}, defaults=defaults)

    async def update_by_field(self, field: str, value: Any, **data) -> Optional[T]:
        """根据字段值更新记录"""
        instance = await self.get_by_field(field, value)
        if not instance:
            return None

        for key, val in data.items():
            if hasattr(instance, key):
                setattr(instance, key, val)

        await instance.save()
        return instance

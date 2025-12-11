# azer_common/repositories/base.py
from typing import TypeVar, Generic, Type, Optional, List, Dict, Any, Tuple
from tortoise.expressions import Q
from tortoise.transactions import in_transaction
from azer_common.models.base import BaseModel

T = TypeVar('T', bound=BaseModel)


class IRepository(Generic[T]):
    """Repository 接口定义"""

    async def get_by_id(self, id: int) -> Optional[T]:
        raise NotImplementedError

    async def get_by_ids(self, ids: List[int]) -> List[T]:
        raise NotImplementedError

    async def exists(self, **filters) -> bool:
        raise NotImplementedError

    async def create(self, **data) -> T:
        raise NotImplementedError

    async def bulk_create(self, data_list: List[Dict[str, Any]]) -> List[T]:
        raise NotImplementedError

    async def update(self, id: int, **data) -> Optional[T]:
        raise NotImplementedError

    async def bulk_update(self, ids: List[int], **data) -> int:
        raise NotImplementedError

    async def delete(self, id: int, soft: bool = True) -> bool:
        raise NotImplementedError

    async def bulk_delete(self, ids: List[int], soft: bool = True) -> int:
        raise NotImplementedError

    async def filter(
            self,
            offset: int = 0,
            limit: int = 20,
            order_by: str = "-created_at",
            **filters
    ) -> Tuple[List[T], int]:
        raise NotImplementedError

    async def search(
            self,
            keyword: str = None,
            search_fields: List[str] = None,
            **filters
    ) -> Tuple[List[T], int]:
        raise NotImplementedError


class BaseRepository(IRepository[T]):
    """基础 Repository 实现"""

    def __init__(self, model: Type[T]):
        self.model = model
        self.soft_delete_field = 'is_deleted'  # 软删除字段名

    async def get_by_id(self, id: int) -> Optional[T]:
        """根据ID获取单个记录"""
        filters = {"id": id}
        if hasattr(self.model, self.soft_delete_field):
            filters[self.soft_delete_field] = False
        return await self.model.get_or_none(**filters)

    async def get_by_ids(self, ids: List[int]) -> List[T]:
        """批量获取记录"""
        query = self.model.filter(id__in=ids)
        if hasattr(self.model, self.soft_delete_field):
            query = query.filter(**{self.soft_delete_field: False})
        return await query.all()

    async def exists(self, **filters) -> bool:
        """检查记录是否存在"""
        if hasattr(self.model, self.soft_delete_field):
            filters[self.soft_delete_field] = False
        return await self.model.filter(**filters).exists()

    async def create(self, **data) -> T:
        """创建记录"""
        return await self.model.create(**data)

    async def bulk_create(self, data_list: List[Dict[str, Any]]) -> List[T]:
        """批量创建记录"""
        return await self.model.bulk_create([self.model(**data) for data in data_list])

    async def update(self, id: int, **data) -> Optional[T]:
        """更新记录"""
        instance = await self.get_by_id(id)
        if not instance:
            return None

        for key, value in data.items():
            if hasattr(instance, key) and not key.startswith('_'):
                setattr(instance, key, value)

        await instance.save()
        return instance

    async def bulk_update(self, ids: List[int], **data) -> int:
        """批量更新记录"""
        return await self.model.filter(
            id__in=ids,
            **{self.soft_delete_field: False} if hasattr(self.model, self.soft_delete_field) else {}
        ).update(**data)

    async def delete(self, id: int, soft: bool = True) -> bool:
        """删除记录（默认软删除）"""
        instance = await self.get_by_id(id)
        if not instance:
            return False

        if soft and hasattr(instance, self.soft_delete_field):
            setattr(instance, self.soft_delete_field, True)
            await instance.save()
            return True
        else:
            await instance.delete()
            return True

    async def bulk_delete(self, ids: List[int], soft: bool = True) -> int:
        """批量删除记录"""
        if soft and hasattr(self.model, self.soft_delete_field):
            update_data = {self.soft_delete_field: True}
            return await self.model.filter(id__in=ids).update(**update_data)
        else:
            return await self.model.filter(id__in=ids).delete()

    async def filter(
            self,
            offset: int = 0,
            limit: int = 20,
            order_by: str = "-created_at",
            **filters
    ) -> Tuple[List[T], int]:
        """通用过滤查询（分页、排序）"""
        query = self.model.all()

        # 自动添加软删除过滤
        if hasattr(self.model, self.soft_delete_field):
            filters[self.soft_delete_field] = False

        # 应用过滤条件
        if filters:
            query = query.filter(**filters)

        # 获取总数
        total = await query.count()

        # 应用排序和分页
        if order_by:
            query = query.order_by(order_by)

        results = await query.offset(offset).limit(limit)
        return list(results), total

    async def search(
            self,
            keyword: str = None,
            search_fields: List[str] = None,
            **filters
    ) -> Tuple[List[T], int]:
        """通用搜索功能"""
        query = self.model.all()

        # 自动添加软删除过滤
        if hasattr(self.model, self.soft_delete_field):
            filters[self.soft_delete_field] = False

        # 应用基础过滤条件
        if filters:
            query = query.filter(**filters)

        # 关键词搜索
        if keyword and search_fields:
            search_q = Q()
            for field in search_fields:
                search_q |= Q(**{f"{field}__icontains": keyword})
            query = query.filter(search_q)

        # 获取总数
        total = await query.count()

        return list(await query.all()), total

    def get_query(self):
        """获取基础查询对象（可用于复杂查询）"""
        query = self.model.all()
        if hasattr(self.model, self.soft_delete_field):
            query = query.filter(**{self.soft_delete_field: False})
        return query

    async def transaction(self):
        """获取事务上下文管理器"""
        return in_transaction()
# azer_common/repositories/base_repository.py
from contextlib import asynccontextmanager
from typing import TypeVar, Generic, Type, Optional, List, Dict, Any, Tuple, Union
from tortoise.expressions import Q
from tortoise.transactions import in_transaction
from azer_common.models.base import BaseModel
from azer_common.utils.time import utc_now

T = TypeVar("T", bound=BaseModel)


class IRepository(Generic[T]):
    """Repository 接口定义"""

    async def get_by_id(self, id: str) -> Optional[T]:
        raise NotImplementedError

    async def get_by_ids(self, ids: List[str]) -> List[T]:
        raise NotImplementedError

    async def exists(self, **filters) -> bool:
        raise NotImplementedError

    async def create(self, **data) -> T:
        raise NotImplementedError

    async def bulk_create(self, data_list: List[Dict[str, Any]]) -> List[T]:
        raise NotImplementedError

    async def update(self, id: str, **data) -> Optional[T]:
        raise NotImplementedError

    async def bulk_update(self, ids: List[str], **data) -> int:
        raise NotImplementedError

    async def delete(self, id: str, soft: bool = True) -> bool:
        raise NotImplementedError

    async def bulk_delete(self, ids: List[str], soft: bool = True) -> int:
        raise NotImplementedError

    async def filter(
        self, offset: int = 0, limit: int = 20, order_by: Union[str, List[str]] = "-created_at", **filters
    ) -> Tuple[List[T], int]:
        raise NotImplementedError

    async def search(self, keyword: str = None, search_fields: List[str] = None, **filters) -> Tuple[List[T], int]:
        raise NotImplementedError


class BaseRepository(IRepository[T]):
    def __init__(self, model: Type[T]):
        self.model = model
        self.soft_delete_field = "is_deleted"
        self.default_search_fields = []
        self.default_order_by = "-created_at"
        self.auto_update_fields = ["updated_at"]
        self.system_protected_fields = ["id", "created_at", "deleted_at", self.soft_delete_field]

    async def create(self, **data) -> T:
        """创建单个记录"""
        if hasattr(self.model, self.soft_delete_field):
            data[self.soft_delete_field] = False
        return await self.model.create(**data)

    async def bulk_create(self, data_list: List[Dict[str, Any]]) -> List[T]:
        """批量创建记录（带事务）"""
        if not data_list:
            return []

        try:
            async with self.transaction():
                for data in data_list:
                    if hasattr(self.model, self.soft_delete_field):
                        data[self.soft_delete_field] = False
                return await self.model.bulk_create([self.model(**data) for data in data_list])
        except Exception:
            raise

    async def get_by_id(self, id: str) -> Optional[T]:
        """根据ID获取单个记录"""
        filters = {"id": id}
        if hasattr(self.model, self.soft_delete_field):
            filters[self.soft_delete_field] = False
        return await self.model.get_or_none(**filters)

    async def get_by_ids(self, ids: List[str]) -> List[T]:
        """批量获取记录"""
        query = self.model.filter(id__in=ids)
        if hasattr(self.model, self.soft_delete_field):
            query = query.filter(**{self.soft_delete_field: False})
        return await query.all()

    async def update(self, id: str, **data) -> Optional[T]:
        """更新单个记录"""
        instance = await self.get_by_id(id)
        if not instance:
            return None

        valid_data = {}
        for key, value in data.items():
            if hasattr(instance, key) and key not in self.system_protected_fields:
                valid_data[key] = value

        if not valid_data:
            return instance

        for key, value in valid_data.items():
            setattr(instance, key, value)

        await instance.save()
        return instance

    async def bulk_update(self, ids: List[str], **data) -> int:
        """批量更新记录（带事务）"""
        if not ids or not data:
            return 0

        valid_data = {k: v for k, v in data.items() if k not in self.system_protected_fields}

        if not valid_data:
            return 0

        for field in self.auto_update_fields:
            if hasattr(self.model, field):
                valid_data[field] = utc_now()
                break

        try:
            async with self.transaction():
                query = self.model.filter(id__in=ids)
                if hasattr(self.model, self.soft_delete_field):
                    query = query.filter(**{self.soft_delete_field: False})
                result = await query.update(**valid_data)
                return result if isinstance(result, int) else 0
        except Exception:
            raise

    async def enhanced_bulk_update(
        self,
        ids: List[str],
        update_data: Dict[str, Any],
        before_update_callback: Optional[callable] = None,
        after_update_callback: Optional[callable] = None,
        **kwargs,
    ) -> Tuple[int, List[T]]:
        """增强型批量更新（支持前后回调）"""
        async with self.transaction():
            if before_update_callback:
                ids = await before_update_callback(ids, update_data, **kwargs)
                if not ids:
                    return 0, []

            updated_count = await self.bulk_update(ids, **update_data)
            updated_records = await self.get_by_ids(ids) if updated_count > 0 else []

            if after_update_callback:
                await after_update_callback(updated_records, **kwargs)

            return updated_count, updated_records

    async def delete(self, id: str, soft: bool = True) -> bool:
        """删除单个记录（默认软删除）"""
        instance = await self.get_by_id(id)
        if not instance:
            return False

        if hasattr(instance, "is_system") and instance.is_system:
            raise ValueError("系统记录不允许删除")

        if soft and hasattr(instance, self.soft_delete_field):
            setattr(instance, self.soft_delete_field, True)
            await instance.save()
            return True
        else:
            await instance.delete()
            return True

    async def bulk_delete(self, ids: List[str], soft: bool = True) -> int:
        """批量删除记录（带事务）"""
        if not ids:
            return 0

        try:
            async with self.transaction():
                if hasattr(self.model, "is_system"):
                    system_count = await self.model.filter(
                        id__in=ids,
                        is_system=True,
                        **{self.soft_delete_field: False} if hasattr(self.model, self.soft_delete_field) else {},
                    ).count()
                    if system_count > 0:
                        raise ValueError("批量删除中包含系统记录")

                if soft and hasattr(self.model, self.soft_delete_field):
                    update_data = {self.soft_delete_field: True, "deleted_at": utc_now()}
                    return await self.model.filter(id__in=ids).update(**update_data)
                else:
                    return await self.model.filter(id__in=ids).delete()
        except Exception:
            raise

    async def exists(self, **filters) -> bool:
        """检查记录是否存在"""
        if hasattr(self.model, self.soft_delete_field):
            filters[self.soft_delete_field] = False
        return await self.model.filter(**filters).exists()

    async def filter(
        self, offset: int = 0, limit: int = 20, order_by: Union[str, List[str]] = None, **filters
    ) -> Tuple[List[T], int]:
        """通用过滤查询（分页、排序）"""
        query = self.model.all()

        if hasattr(self.model, self.soft_delete_field):
            filters[self.soft_delete_field] = False

        if filters:
            query = query.filter(**filters)

        total = await query.count()

        if order_by is None:
            order_by = self.default_order_by

        if order_by:
            query = query.order_by(order_by)

        if limit > 0:
            query = query.offset(offset).limit(limit)

        results = await query.all()
        return list(results), total

    async def search(self, keyword: str = None, search_fields: List[str] = None, **filters) -> Tuple[List[T], int]:
        """通用搜索功能"""
        query = self.model.all()

        if hasattr(self.model, self.soft_delete_field):
            filters[self.soft_delete_field] = False

        if filters:
            query = query.filter(**filters)

        if keyword and keyword.strip():
            if search_fields is None:
                search_fields = self.default_search_fields

            if search_fields:
                search_q = Q()
                for field in search_fields:
                    search_q |= Q(**{f"{field}__icontains": keyword})
                query = query.filter(search_q)

        total = await query.count()
        query = query.order_by(self.default_order_by)

        return list(await query.all()), total

    async def get_or_create(self, defaults: Dict[str, Any] = None, **kwargs) -> Tuple[T, bool]:
        """获取或创建记录"""
        if defaults is None:
            defaults = {}

        if hasattr(self.model, self.soft_delete_field):
            kwargs[self.soft_delete_field] = False

        instance = await self.model.get_or_none(**kwargs)
        if instance:
            return instance, False

        create_data = {**kwargs, **defaults}
        if hasattr(self.model, self.soft_delete_field):
            create_data[self.soft_delete_field] = False

        instance = await self.model.create(**create_data)
        return instance, True

    async def update_or_create(self, defaults: Dict[str, Any] = None, **kwargs) -> Tuple[T, bool]:
        """更新或创建记录"""
        if defaults is None:
            defaults = {}

        if hasattr(self.model, self.soft_delete_field):
            kwargs[self.soft_delete_field] = False

        instance = await self.model.get_or_none(**kwargs)
        if instance:
            for key, value in defaults.items():
                setattr(instance, key, value)
            await instance.save()
            return instance, False

        create_data = {**kwargs, **defaults}
        if hasattr(self.model, self.soft_delete_field):
            create_data[self.soft_delete_field] = False

        instance = await self.model.create(**create_data)
        return instance, True

    async def count(self, **filters) -> int:
        """统计记录数量"""
        if hasattr(self.model, self.soft_delete_field):
            filters[self.soft_delete_field] = False
        return await self.model.filter(**filters).count()

    async def distinct_values(self, field: str, **filters) -> List[Any]:
        """获取字段的唯一值列表"""
        if hasattr(self.model, self.soft_delete_field):
            filters[self.soft_delete_field] = False
        return await self.model.filter(**filters).distinct().values_list(field, flat=True)

    @asynccontextmanager
    async def transaction(self):
        """事务管理器"""
        try:
            async with in_transaction() as transaction:
                yield transaction
        except Exception:
            raise

    def get_query(self):
        """获取基础查询对象（已过滤软删除）"""
        query = self.model.all()
        if hasattr(self.model, self.soft_delete_field):
            query = query.filter(**{self.soft_delete_field: False})
        return query

# azer_common/models/base.py
from uuid_extensions import uuid7
from tortoise import fields, models
from tortoise.manager import Manager

from azer_common.utils.time import utc_now


class SoftDeleteManager(Manager):
    """自动过滤软删除数据的默认管理器"""

    def get_queryset(self):
        # 重写查询集，默认过滤已删除数据
        return super().get_queryset().filter(is_deleted=False)


class BaseModel(models.Model):
    """基础模型，包含通用字段"""

    # 主键
    id = fields.UUIDField(pk=True, field_type="BINARY(16)", default=uuid7)

    # 审计字段
    created_at = fields.DatetimeField(auto_now_add=True, description='创建时间')
    updated_at = fields.DatetimeField(auto_now=True, description='更新时间')

    # 软删除字段
    is_deleted = fields.BooleanField(default=False, description='是否删除')
    deleted_at = fields.DatetimeField(null=True, description='删除时间')

    # 元数据字段
    meta = fields.JSONField(null=True, description='元数据', default=dict)

    # 配置默认管理器（自动过滤软删除）
    objects = SoftDeleteManager()
    # 保留原始管理器（如需查询已删除数据时使用）
    all_objects = Manager()

    class Meta:
        abstract = True
        ordering = ["-created_at"]

    def __repr__(self):
        return f"<{self.__class__.__name__}: {self.id}>"

    async def soft_delete(self):
        """
        软删除当前实例：标记is_deleted=True，记录deleted_at时间
        """
        self.is_deleted = True
        self.deleted_at = utc_now()
        await self.save(update_fields=["is_deleted", "deleted_at"])

    async def restore(self):
        """
        恢复软删除实例：标记is_deleted=False，清空deleted_at时间
        """
        self.is_deleted = False
        self.deleted_at = None
        await self.save(update_fields=["is_deleted", "deleted_at"])

    class PydanticMeta:
        exclude = ("is_deleted", "deleted_at")

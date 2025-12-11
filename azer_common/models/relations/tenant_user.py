from tortoise import fields
from azer_common.models.base import BaseModel
from azer_common.utils.time import utc_now


class TenantUser(BaseModel):
    """租户-用户关联表 """
    tenant = fields.ForeignKeyField(
        'models.Tenant',
        related_name='tenant_users',
        on_delete=fields.RESTRICT,
        description='关联租户',
        null=False
    )
    user = fields.ForeignKeyField(
        'models.User',
        related_name='user_tenants',
        on_delete=fields.RESTRICT,
        description='关联用户',
        null=False
    )

    is_primary = fields.BooleanField(
        default=False,
        description='是否用户的主租户（一个用户仅一个主租户）'
    )
    is_assigned = fields.BooleanField(
        default=True,
        description='是否已分配（取消分配则置为False）'
    )
    expires_at = fields.DatetimeField(
        null=True,
        description='关联过期时间（null表示永久有效）'
    )
    metadata = fields.JSONField(
        null=True,
        description='关联元数据（如分配原因、权限范围）'
    )

    class Meta:
        table = "azer_tenant_user"
        table_description = '租户-用户关联表'
        # 优化唯一约束：1. 软删除+租户+用户唯一 2. 未删除状态下用户仅一个主租户
        unique_together = [
            ("tenant_id", "user_id", "is_deleted"),
            ("user_id", "is_primary", "is_deleted")
        ]
        # 优化索引：聚焦高频查询场景
        indexes = [
            ("tenant_id", "is_assigned", "is_deleted"),   # 查租户下有效用户
            ("user_id", "is_primary", "is_assigned"),     # 查用户主租户/有效租户
            ("expires_at", "is_assigned", "is_deleted"),  # 查过期待清理的关联
            ("tenant_id", "user_id", "is_assigned"),      # 高频：租户+用户+分配状态
        ]

    def __str__(self):
        # 优化：兼容租户/用户未加载的边界情况
        tenant_code = getattr(self.tenant, 'code', self.tenant_id) if self.tenant_id else '未知租户'
        username = getattr(self.user, 'username', self.user_id) if self.user_id else '未知用户'
        return f"租户[{tenant_code}] - 用户[{username}]"

    async def save(self, *args, **kwargs):
        """保存前基础校验"""
        # 基础非空校验
        if not self.tenant_id or not self.user_id:
            raise ValueError("租户ID和用户ID不能为空")
        # 轻量逻辑校验
        await self.validate()
        await super().save(*args, **kwargs)

    async def validate(self) -> None:
        """模型层轻量校验（复杂校验抽离到仓储层）"""
        # 1. 时间逻辑校验
        now = utc_now()
        if self.expires_at and self.expires_at <= now:
            raise ValueError(f"过期时间({self.expires_at})不能早于当前时间({now})")
        # 2. 主租户状态校验：已过期/未分配的关联不能设为主租户
        if self.is_primary and (not self.is_assigned or (self.expires_at and self.expires_at <= now)):
            raise ValueError("已过期/未分配的租户关联不能设为主租户")

    async def soft_delete(self):
        """重写软删除：同步标记为未分配"""
        self.is_deleted = True
        self.deleted_at = utc_now()
        self.is_assigned = False
        self.is_primary = False
        await self.save(update_fields=["is_deleted", "deleted_at", "is_assigned", "is_primary"])
        return self

    @property
    def is_valid(self) -> bool:
        """检查关联是否有效（已分配+未过期+未软删除）"""
        if not self.is_assigned or self.is_deleted:
            return False
        if self.expires_at and self.expires_at < utc_now():
            return False
        return True

    class PydanticMeta:
        include = {
            "tenant": {"id", "code", "name"},
            "user": {"id", "username", "display_name"},
        }

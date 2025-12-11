from tortoise import fields
from azer_common.models.base import BaseModel
from azer_common.utils.time import utc_now


class TenantUser(BaseModel):
    """租户用户关联表，管理用户与租户的归属关系"""
    # 核心关联字段
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

    # 状态控制字段
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
        unique_together = [
            ("tenant_id", "user_id", "is_deleted"),
            ("user_id", "is_primary", "is_deleted")
        ]
        indexes = [
            ("tenant_id", "is_assigned", "is_deleted"),
            ("user_id", "is_primary", "is_assigned"),
            ("expires_at", "is_assigned", "is_deleted"),
            ("tenant_id", "user_id", "is_assigned"),
        ]

    class PydanticMeta:
        include = {
            "tenant": {"id", "code", "name"},
            "user": {"id", "username", "display_name"},
        }

    def __str__(self):
        """租户用户关联实例的字符串表示，兼容关联未加载场景"""
        tenant_code = getattr(self.tenant, 'code', self.tenant_id) if self.tenant_id else '未知租户'
        username = getattr(self.user, 'username', self.user_id) if self.user_id else '未知用户'
        return f"租户[{tenant_code}] - 用户[{username}]"

    async def save(self, *args, **kwargs):
        """保存关联前执行基础校验，验证通过后调用父类保存方法"""
        if not self.tenant_id or not self.user_id:
            raise ValueError("租户ID和用户ID不能为空")
        await self.validate()
        await super().save(*args, **kwargs)

    async def validate(self):
        """验证租户用户关联数据合法性"""
        # 时间逻辑校验
        now = utc_now()
        if self.expires_at and self.expires_at <= now:
            raise ValueError(f"过期时间({self.expires_at})不能早于当前时间({now})")

        # 主租户状态校验
        if self.is_primary and (not self.is_assigned or (self.expires_at and self.expires_at <= now)):
            raise ValueError("已过期/未分配的租户关联不能设为主租户")

    async def soft_delete(self):
        """软删除关联关系，同步取消主租户标记和分配状态"""
        self.is_deleted = True
        self.is_assigned = False
        self.is_primary = False
        await self.save(update_fields=["is_deleted", "deleted_at", "is_assigned", "is_primary"])
        return self

    @property
    def is_expired(self) -> bool:
        """检查租户用户关联是否过期"""
        if not self.expires_at:
            return False
        return utc_now() >= self.expires_at

    @property
    def is_valid(self) -> bool:
        """检查租户用户关联是否有效（已分配+未过期+未软删除）"""
        if not self.is_assigned or self.is_deleted:
            return False
        return not self.is_expired
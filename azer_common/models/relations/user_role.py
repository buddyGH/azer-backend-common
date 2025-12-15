from tortoise import fields

from azer_common.models.audit.registry import register_audit
from azer_common.models.base import BaseModel
from azer_common.utils.time import utc_now


@register_audit(business_type="user_role", signals=["post_save", "post_delete"])
class UserRole(BaseModel):
    """用户角色关联表，管理用户在租户下的角色分配关系"""

    # 核心关联字段
    user = fields.ForeignKeyField(
        "models.User", related_name="user_roles", description="关联用户", on_delete=fields.RESTRICT, null=False
    )
    role = fields.ForeignKeyField(
        "models.Role", related_name="role_users", description="关联角色", on_delete=fields.RESTRICT, null=False
    )
    tenant = fields.ForeignKeyField(
        "models.Tenant",
        related_name="user_roles",
        description="所属租户（强关联）",
        on_delete=fields.RESTRICT,
        null=False,
        index=True,
    )

    # 状态控制字段
    is_assigned = fields.BooleanField(default=True, description="是否分配（用户-角色关联关系是否有效）")
    expires_at = fields.DatetimeField(null=True, description="到期时间（null表示永久有效）")
    metadata = fields.JSONField(null=True, description="扩展元数据")

    class Meta:
        table = "azer_user_role"
        table_description = "用户角色关系表（核心关联表）"
        unique_together = [("user_id", "role_id", "tenant_id", "is_deleted"), ("user_id", "role_id", "tenant_id")]
        indexes = [
            ("tenant_id", "user_id", "is_assigned", "is_deleted"),
            ("tenant_id", "role_id", "is_assigned", "is_deleted"),
            ("expires_at", "is_assigned", "is_deleted"),
        ]

    class PydanticMeta:
        include = {
            "user": {"id", "username", "display_name"},
            "role": {"id", "code", "name"},
            "tenant": {"id", "code", "name"},
        }

    def __str__(self):
        """用户角色关联实例的字符串表示"""
        tenant_info = f"[租户:{self.tenant_id}]"
        valid_status = "有效" if self.is_valid else "无效"
        return f"{tenant_info} 用户({self.user_id})-角色({self.role_id}) [{valid_status}]"

    async def save(self, *args, **kwargs):
        """保存关联前执行基础校验，验证通过后调用父类保存方法"""
        if not self.user_id or not self.role_id or not self.tenant_id:
            raise ValueError("用户ID、角色ID、租户ID不能为空")
        await self.validate()
        await super().save(*args, **kwargs)

    async def validate(self):
        """验证用户角色关联数据合法性"""
        now = utc_now()
        if self.expires_at and self.expires_at <= now:
            raise ValueError(f"过期时间({self.expires_at})不能早于当前时间({now})")
        if self.is_assigned and self.is_expired:
            raise ValueError("已过期的角色关联不能标记为'已分配'")

    async def soft_delete(self):
        """软删除关联关系，同步标记为未分配"""
        self.is_deleted = True
        self.is_assigned = False
        await self.save(update_fields=["is_deleted", "deleted_at", "is_assigned"])
        return self

    @property
    def is_expired(self) -> bool:
        """检查用户角色关联是否过期"""
        if not self.expires_at:
            return False
        return utc_now() >= self.expires_at

    @property
    def is_valid(self) -> bool:
        """检查用户角色关联是否有效（已分配+未过期+未软删除）"""
        return self.is_assigned and not self.is_expired and not self.is_deleted

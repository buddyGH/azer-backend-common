from tortoise.exceptions import DoesNotExist
from azer_common.models.base import BaseModel
from tortoise import fields
from azer_common.models.role.model import Role
from azer_common.models.user.model import User
from azer_common.utils.time import utc_now


class UserRole(BaseModel):
    # 核心关联字段（级联删除：用户/角色删除则关联自动删除）
    user = fields.ForeignKeyField(
        'models.User',
        related_name='user_roles',
        description='用户',
        on_delete=fields.RESTRICT,
        null=False
    )
    role = fields.ForeignKeyField(
        'models.Role',
        related_name='role_users',
        description='角色',
        on_delete=fields.RESTRICT,
        null=False
    )

    # ========== 关键修正：多租户字段优化 ==========
    tenant = fields.ForeignKeyField(
        'models.Tenant',
        related_name='user_roles',
        description='所属租户（外键，保证数据一致性）',
        on_delete=fields.RESTRICT,
        null=False,
        index=True
    )

    # 核心业务状态字段
    is_assigned = fields.BooleanField(
        default=True,
        description='是否分配（用户-角色关联关系是否有效）'
    )
    expires_at = fields.DatetimeField(
        null=True,
        description='到期时间（null表示永久有效）'
    )
    metadata = fields.JSONField(
        null=True,
        description='扩展元数据'
    )

    class Meta:
        unique_together = [
            ("user_id", "role_id", "tenant_id", "is_deleted"),
            # 补充：未删除状态下，用户-角色-租户 必须唯一（核心约束）
            ("user_id", "role_id", "tenant_id"),
        ]
        indexes = [
            # 高频查询：租户+用户+有效状态（查询用户在租户下的有效角色）
            ("tenant_id", "user_id", "is_assigned", "is_deleted"),
            # 高频查询：租户+角色+有效状态（查询角色在租户下的所有用户）
            ("tenant_id", "role_id", "is_assigned", "is_deleted"),
            # 过期清理：过期时间+有效状态
            ("expires_at", "is_assigned", "is_deleted"),
        ]

    def __str__(self):
        tenant_info = f"[租户:{self.tenant_id}]"
        valid_status = "有效" if self.is_valid() else "无效"
        return f"{tenant_info} 用户({self.user_id})-角色({self.role_id}) [{valid_status}]"

    async def save(self, *args, **kwargs):
        if not self.user_id or not self.role_id or not self.tenant_id:
            raise ValueError("用户ID、角色ID、租户ID不能为空")
        await self.validate()
        await super().save(*args, **kwargs)

    async def validate(self):
        now = utc_now()
        if self.expires_at and self.expires_at <= now:
            raise ValueError(f"过期时间({self.expires_at})不能早于当前时间({now})")
        if self.is_assigned and self.is_expired():
            raise ValueError("已过期的角色关联不能标记为'已分配'")

    async def soft_delete(self):
        """重写软删除：同步标记为未分配"""
        self.is_deleted = True
        self.is_assigned = False
        await self.save(update_fields=["is_deleted", "deleted_at", "is_assigned"])
        return self

    def is_expired(self) -> bool:
        """检查角色是否过期（UTC时间）"""
        if not self.expires_at:
            return False
        return utc_now() >= self.expires_at

    def is_valid(self) -> bool:
        """检查角色是否有效（未过期+未撤销+未删除）"""
        return self.is_assigned and not self.is_expired() and not self.is_deleted

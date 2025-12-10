# azer_common/models/relations/user_role.py
from datetime import timedelta
from azer_common.models.base import BaseModel
from tortoise import fields
from azer_common.utils.time import utc_now


class UserRole(BaseModel):
    user = fields.ForeignKeyField(
        'models.User',
        related_name='user_roles',
        description='用户',
        on_delete=fields.CASCADE,
    )
    role = fields.ForeignKeyField(
        'models.Role',
        related_name='role_users',
        description='角色',
        on_delete=fields.CASCADE
    )
    granted_by = fields.ForeignKeyField(
        'models.User',
        related_name='granted_roles',
        null=True,
        description='授予该角色的用户（为空则表示系统分配）',
        on_delete=fields.SET_NULL
    )
    granted_at = fields.DatetimeField(
        default=utc_now,
        description='授予时间'
    )
    expires_at = fields.DatetimeField(
        null=True,
        description='到期时间'
    )
    is_active = fields.BooleanField(
        default=True,
        description='是否激活'
    )
    revoked_at = fields.DatetimeField(
        null=True,
        description='撤销时间'
    )
    revoked_by = fields.ForeignKeyField(
        'models.User',
        related_name='revoked_roles',
        null=True,
        description='撤销者',
        on_delete=fields.SET_NULL
    )
    reason = fields.CharField(
        max_length=200,
        null=True,
        description='授予/撤销原因'
    )

    class Meta:
        table = "azer_user_role"
        unique_together = ("user", "role", "is_active")
        table_description = '用户角色关系表'
        indexes = [
            ("user", "is_active", "expires_at"),
            ("expires_at", "is_active"),
            ("role", "is_active"),
        ]

    async def save(self, *args, **kwargs):
        """保存前验证"""
        await self.validate()
        await super().save(*args, **kwargs)

    async def validate(self):
        """验证数据有效性"""
        # 1. 不能同时有 expires_at 和 revoked_at
        if self.expires_at and self.revoked_at:
            raise ValueError("角色不能同时设置过期时间和撤销时间")

        # 2. 过期时间必须在授予时间之后
        if self.expires_at and self.expires_at <= self.granted_at:
            raise ValueError("过期时间必须在授予时间之后")

        # 3. 撤销时间必须在授予时间之后
        if self.revoked_at and self.revoked_at <= self.granted_at:
            raise ValueError("撤销时间必须在授予时间之后")

        # 4. 如果被撤销，is_active 应为 False
        if self.revoked_at and self.is_active:
            self.is_active = False

    def is_expired(self) -> bool:
        """检查角色是否过期"""
        if not self.expires_at:
            return False
        return utc_now() >= self.expires_at

    def is_valid(self) -> bool:
        """检查角色是否有效（未过期且未撤销）"""
        return self.is_active and not self.is_expired() and not self.revoked_at

    @classmethod
    async def grant_role(
            cls,
            user,
            role,
            granted_by=None,
            expires_in_days: int = None,
            reason: str = None
    ):
        """授予角色（工厂方法）"""
        expires_at = None
        if expires_in_days:
            expires_at = utc_now() + timedelta(days=expires_in_days)

        # 检查是否已存在有效角色
        existing = await cls.filter(
            user=user,
            role=role,
            is_active=True
        ).first()

        if existing and existing.is_valid():
            raise ValueError("用户已拥有该有效角色")

        user_role = cls(
            user=user,
            role=role,
            granted_by=granted_by,
            expires_at=expires_at,
            reason=reason
        )
        await user_role.save()
        return user_role

    async def revoke(self, revoked_by=None, reason: str = None):
        """撤销角色"""
        self.is_active = False
        self.revoked_at = utc_now()
        self.revoked_by = revoked_by
        self.reason = reason
        await self.save()

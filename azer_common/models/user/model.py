# azer_common/models/user/model.py
from typing import Dict, List, Optional, Union
from tortoise import fields
from tortoise.expressions import Q
from azer_common.models.base import BaseModel
from azer_common.models.enums.base import SexEnum, UserStatusEnum
from azer_common.models.relations.tenant_user import TenantUser
from azer_common.models.relations.user_role import UserRole
from azer_common.models.role.model import Role
from azer_common.models.tenant.model import Tenant
from azer_common.utils.time import utc_now, today
from azer_common.utils.validators import (
    validate_url, validate_username, validate_email,
    validate_mobile, validate_identity_card
)


class User(BaseModel):
    """用户表 - 存储用户核心信息和业务状态"""

    # 账户信息
    username = fields.CharField(
        max_length=30,
        unique=True,
        validators=[validate_username],
        description='用户名',
        index=True
    )

    # 账户状态
    status = fields.CharEnumField(
        UserStatusEnum,
        default=UserStatusEnum.UNVERIFIED,
        description='用户核心状态'
    )

    # 个人身份信息
    real_name = fields.CharField(
        max_length=30,
        null=True,
        description="用户全名"
    )
    identity_card = fields.CharField(
        max_length=18,
        null=True,
        unique=True,
        validators=[validate_identity_card],
        description="身份证号",
        index=True
    )

    # 联系信息
    email = fields.CharField(
        max_length=100,
        null=True,
        unique=True,
        validators=[validate_email],
        description='邮箱',
        index=True
    )
    mobile = fields.CharField(
        max_length=15,
        null=True,
        unique=True,
        validators=[validate_mobile],
        description='手机号',
        index=True
    )

    # 用户资料
    nick_name = fields.CharField(
        max_length=50,
        null=True,
        description='昵称'
    )
    sex = fields.CharEnumField(
        SexEnum,
        default=SexEnum.OTHER,
        description='性别'
    )
    birth_date = fields.DateField(
        null=True,
        description='出生日期'
    )
    avatar = fields.CharField(
        max_length=500,
        null=True,
        validators=[validate_url],
        description='头像URL'
    )
    desc = fields.TextField(
        null=True,
        description='个人简介'
    )
    home_path = fields.CharField(
        max_length=500,
        null=True,
        description='个人主页路径'
    )
    preferences = fields.JSONField(
        null=True,
        description='用户偏好设置',
        default=dict
    )

    # 关系字段
    roles = fields.ManyToManyField(
        'models.Role',
        related_name='users',
        through='azer_user_role',
        description='用户角色'
    )

    tenants = fields.ManyToManyField(
        'models.Tenant',
        related_name='users',
        through='azer_tenant_user',
        description='用户属于多个租户'
    )

    class Meta:
        table = "azer_user"
        table_description = '用户表'
        indexes = [
            ("status", "created_at"),  # 状态+创建时间索引
        ]

    def __str__(self):
        """用户友好的字符串表示"""
        return f"{self.username} ({self.real_name or self.nick_name})"

    # 便捷属性访问
    @property
    def is_active(self) -> bool:
        """检查用户是否处于活跃状态"""
        return self.status == UserStatusEnum.ACTIVE

    @property
    def display_name(self) -> str:
        """获取显示名称（优先顺序）"""
        return self.real_name or self.nick_name or self.username

    @property
    def age(self) -> Optional[int]:
        """计算年龄"""
        if not self.birth_date:
            return None
        _today = today()
        return _today.year - self.birth_date.year - (
                (_today.month, _today.day) < (self.birth_date.month, self.birth_date.day)
        )

    # 用户偏好便捷方法
    def get_preference(self, key: str, default=None):
        """安全获取用户偏好设置"""
        return self.preferences.get(key, default) if self.preferences else default

    def set_preference(self, key: str, value):
        """安全设置用户偏好"""
        if not self.preferences:
            self.preferences = {}
        self.preferences[key] = value

    # ========== 便捷方法（封装 UserRole 操作） ==========
    async def assign_role(
            self,
            role: Union[int, Role],
            expires_in_days: int = None,
            metadata: Optional[Dict] = None
    ) -> UserRole:
        """
        给当前用户分配单个角色
        :return: 创建的 UserRole 实例
        """
        return await UserRole.grant_role(
            user=self,
            role=role,
            expires_in_days=expires_in_days,
            metadata=metadata
        )

    async def assign_roles(
            self,
            roles: List[Union[int, Role]],
            expires_in_days: int = None,
            metadata: Optional[Dict] = None
    ) -> Dict[str, any]:
        """
        给当前用户批量分配角色
        :return: 批量创建结果（created/existing 等）
        """
        return await UserRole.bulk_grant_roles(
            user=self,
            roles=roles,
            expires_in_days=expires_in_days,
            metadata=metadata
        )

    async def revoke_role(self, role: Union[int, Role]) -> bool:
        """
        撤销当前用户的单个角色
        :return: 是否成功撤销
        """
        return await UserRole.revoke_role(user=self, role=role)

    async def revoke_roles(self, roles: List[Union[int, Role]]) -> int:
        """
        批量撤销当前用户的指定角色
        :return: 成功撤销的数量
        """
        return await UserRole.bulk_revoke_roles(user=self, roles=roles)

    async def revoke_all_roles(self) -> int:
        """
        撤销当前用户的所有有效角色
        :return: 成功撤销的数量
        """
        return await UserRole.bulk_revoke_roles(user=self)

    async def get_roles(
            self,
            include_expired: bool = False,
            include_revoked: bool = False
    ) -> List[Role]:
        """
        获取当前用户的角色列表（返回 Role 实例，而非 UserRole）
        :return: 角色实例列表
        """
        user_roles = await UserRole.get_user_roles(
            user=self,
            include_expired=include_expired,
            include_revoked=include_revoked
        )
        # 提取 Role 实例
        return [ur.role for ur in user_roles]

    async def get_valid_roles(self) -> List[Role]:
        """
        快捷获取当前用户的有效角色（未过期+未撤销）
        """
        return await self.get_roles(include_expired=False, include_revoked=False)

    async def has_role(
            self,
            role: Union[int, Role, str],
            check_valid: bool = True
    ) -> bool:
        """
        检查当前用户是否拥有指定角色（支持ID/实例/编码）
        :param role: 角色ID/实例/编码
        :param check_valid: 是否仅检查有效角色（未过期+未撤销）
        """
        return await UserRole.has_role(
            user=self,
            role=role,
            check_valid=check_valid
        )

    async def refresh_role_expiry(
            self,
            role: Union[int, Role],
            expires_in_days: int
    ) -> bool:
        """
        刷新指定角色的过期时间
        :return: 是否成功更新
        """
        return await UserRole.refresh_expires_at(
            user=self,
            role=role,
            expires_in_days=expires_in_days
        )

    # ========== 租户相关方法 ==========
    async def get_tenants(self) -> List[Tenant]:
        """
        获取用户所属的所有租户
        """
        return await self.tenants.filter(is_deleted=False).all()

    async def get_primary_tenant(self) -> Optional[Tenant]:
        """
        获取用户的主租户
        """
        tenant_user = await TenantUser.objects.filter(
            user=self,
            is_primary=True,
            is_assigned=True,
            is_deleted=False
        ).first()
        return tenant_user.tenant if tenant_user else None

    # ========== 带租户参数的角色方法 ==========
    async def assign_role_in_tenant(
            self,
            role: Union[int, Role],
            tenant: Union[int, Tenant],
            expires_in_days: int = None,
            metadata: Optional[Dict] = None
    ) -> UserRole:
        """
        在指定租户下为用户分配角色
        """
        # 检查用户是否属于该租户
        if not await TenantUser.has_user(tenant=tenant, user=self, check_valid=True):
            raise ValueError(f"用户[{self.username}]不属于租户[{tenant.code}]")

        # 检查角色是否属于该租户
        role_obj = await Role.objects.get(id=role) if isinstance(role, int) else role
        if role_obj.tenant_id != (tenant.id if isinstance(tenant, Tenant) else tenant):
            raise ValueError("角色不属于指定租户")

        return await UserRole.grant_role(
            user=self,
            role=role,
            expires_in_days=expires_in_days,
            metadata=metadata
        )

    async def get_roles_in_tenant(
            self,
            tenant: Union[int, Tenant],
            include_expired: bool = False,
            include_revoked: bool = False
    ) -> List[Role]:
        """
        获取用户在指定租户下的角色
        """
        user_roles = await UserRole.get_user_roles(
            user=self,
            include_expired=include_expired,
            include_revoked=include_revoked,
            tenant_id=tenant.id if isinstance(tenant, Tenant) else tenant
        )
        return [ur.role for ur in user_roles]

    async def has_role_in_tenant(
            self,
            role: Union[int, Role, str],
            tenant: Union[int, Tenant],
            check_valid: bool = True
    ) -> bool:
        """
        检查用户在指定租户下是否拥有指定角色
        """
        return await UserRole.has_role(
            user=self,
            role=role,
            check_valid=check_valid,
            tenant_id=tenant.id if isinstance(tenant, Tenant) else tenant
        )

import azer_common.models.user.signals

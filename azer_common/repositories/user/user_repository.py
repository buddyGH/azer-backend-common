# azer_common/repositories/user/user_repository.py
from typing import Dict, List, Optional, Union
import uuid
from azer_common.models.user.model import User
from azer_common.models.role.model import Role
from azer_common.models.tenant.model import Tenant
from azer_common.models.relations.tenant_user import TenantUser
from azer_common.models.relations.user_role import UserRole


class UserRepository:
    """用户仓储层：封装所有用户相关的数据访问逻辑"""

    # ========== 角色相关操作 ==========
    @classmethod
    async def assign_role(
            cls,
            user: User,
            role: Union[uuid.UUID, Role],
            expires_in_days: int = None,
            metadata: Optional[Dict] = None
    ) -> UserRole:
        """给用户分配单个角色"""
        return await UserRole.grant_role(
            user=user,
            role=role,
            expires_in_days=expires_in_days,
            metadata=metadata
        )

    @classmethod
    async def assign_roles(
            cls,
            user: User,
            roles: List[Union[uuid.UUID, Role]],
            expires_in_days: int = None,
            metadata: Optional[Dict] = None
    ) -> Dict[str, any]:
        """批量分配角色"""
        return await UserRole.bulk_grant_roles(
            user=user,
            roles=roles,
            expires_in_days=expires_in_days,
            metadata=metadata
        )

    @classmethod
    async def get_roles(
            cls,
            user: User,
            include_expired: bool = False,
            include_revoked: bool = False
    ) -> List[Role]:
        """获取用户的角色列表"""
        user_roles = await UserRole.get_user_roles(
            user=user,
            include_expired=include_expired,
            include_revoked=include_revoked
        )
        return [ur.role for ur in user_roles]

    # ========== 租户相关操作 ==========
    @classmethod
    async def get_tenants(cls, user: User) -> List[Tenant]:
        """获取用户所属的所有租户"""
        return await user.tenants.filter(is_deleted=False).all()

    @classmethod
    async def get_primary_tenant(cls, user: User) -> Optional[Tenant]:
        """获取用户的主租户"""
        tenant_user = await TenantUser.objects.filter(
            user=user,
            is_primary=True,
            is_assigned=True,
            is_deleted=False
        ).first()
        return tenant_user.tenant if tenant_user else None

    # ========== 租户+角色关联操作 ==========
    @classmethod
    async def assign_role_in_tenant(
            cls,
            user: User,
            role: Union[uuid.UUID, Role],
            tenant: Union[uuid.UUID, Tenant],
            expires_in_days: int = None,
            metadata: Optional[Dict] = None
    ) -> UserRole:
        """在指定租户下为用户分配角色"""
        # 检查用户是否属于该租户
        tenant_id = tenant.id if isinstance(tenant, Tenant) else tenant
        if not await TenantUser.has_user(tenant=tenant_id, user=user, check_valid=True):
            raise ValueError(f"用户[{user.username}]不属于租户[{tenant_id}]")

        # 检查角色是否属于该租户
        role_obj = await Role.objects.get(id=role) if isinstance(role, uuid.UUID) else role
        if role_obj.tenant_id != tenant_id:
            raise ValueError("角色不属于指定租户")

        return await UserRole.grant_role(
            user=user,
            role=role_obj,
            expires_in_days=expires_in_days,
            metadata=metadata
        )

    @classmethod
    async def get_roles_in_tenant(
            cls,
            user: User,
            tenant: Union[uuid.UUID, Tenant],
            include_expired: bool = False,
            include_revoked: bool = False
    ) -> List[Role]:
        """获取用户在指定租户下的角色"""
        tenant_id = tenant.id if isinstance(tenant, Tenant) else tenant
        user_roles = await UserRole.get_user_roles(
            user=user,
            include_expired=include_expired,
            include_revoked=include_revoked,
            tenant_id=tenant_id
        )
        return [ur.role for ur in user_roles]

    @classmethod
    async def has_role_in_tenant(
            cls,
            user: User,
            role: Union[uuid.UUID, Role, str],
            tenant: Union[uuid.UUID, Tenant],
            check_valid: bool = True
    ) -> bool:
        """检查用户在指定租户下是否拥有指定角色"""
        tenant_id = tenant.id if isinstance(tenant, Tenant) else tenant
        return await UserRole.has_role(
            user=user,
            role=role,
            check_valid=check_valid,
            tenant_id=tenant_id
        )

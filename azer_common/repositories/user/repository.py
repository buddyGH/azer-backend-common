# azer_common/repositories/user/repository.py
from typing import Dict, List, Optional, Union, Any, Tuple
from tortoise.expressions import Q
from azer_common.models.user.model import User
from azer_common.models.enums.base import UserStatusEnum
from azer_common.models.relations.tenant_user import TenantUser
from azer_common.models.relations.user_role import UserRole
from azer_common.models.role.model import Role
from azer_common.models.tenant.model import Tenant
from azer_common.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    """用户数据访问层"""

    def __init__(self):
        super().__init__(User)
        self.default_search_fields = ['username', 'nick_name', 'real_name', 'email', 'mobile']

    # ========== 特定查询方法 ==========

    async def get_by_username(self, username: str) -> Optional[User]:
        """根据用户名获取用户"""
        return await self.get_query().filter(username=username).first()

    async def get_by_email(self, email: str) -> Optional[User]:
        """根据邮箱获取用户"""
        return await self.get_query().filter(email=email).first()

    async def get_by_mobile(self, mobile: str) -> Optional[User]:
        """根据手机号获取用户"""
        return await self.get_query().filter(mobile=mobile).first()

    async def get_by_identity_card(self, identity_card: str) -> Optional[User]:
        """根据身份证号获取用户"""
        return await self.get_query().filter(identity_card=identity_card).first()

    async def exists_by_username(self, username: str, exclude_user_id: int = None) -> bool:
        """检查用户名是否存在"""
        query = self.get_query().filter(username=username)
        if exclude_user_id:
            query = query.exclude(id=exclude_user_id)
        return await query.exists()

    async def exists_by_email(self, email: str, exclude_user_id: int = None) -> bool:
        """检查邮箱是否存在"""
        query = self.get_query().filter(email=email)
        if exclude_user_id:
            query = query.exclude(id=exclude_user_id)
        return await query.exists()

    async def exists_by_mobile(self, mobile: str, exclude_user_id: int = None) -> bool:
        """检查手机号是否存在"""
        query = self.get_query().filter(mobile=mobile)
        if exclude_user_id:
            query = query.exclude(id=exclude_user_id)
        return await query.exists()

    async def create_user(
            self,
            username: str,
            email: Optional[str] = None,
            mobile: Optional[str] = None,
            real_name: Optional[str] = None,
            **kwargs
    ) -> User:
        """创建新用户"""
        user_data = {
            'username': username,
            'email': email,
            'mobile': mobile,
            'real_name': real_name,
            **kwargs
        }
        return await self.create(**user_data)

    async def update_status(self, user_id: int, status: UserStatusEnum) -> bool:
        """更新用户状态"""
        return await self.update(user_id, status=status) is not None

    async def bulk_update_status(
            self,
            user_ids: List[int],
            status: UserStatusEnum
    ) -> int:
        """批量更新用户状态"""
        return await self.bulk_update(user_ids, status=status)

    async def get_active_users_count(self) -> int:
        """获取活跃用户数量"""
        return await self.get_query().filter(status=UserStatusEnum.ACTIVE).count()

    async def get_users_by_birth_month(
            self,
            month: int,
            status: Optional[UserStatusEnum] = UserStatusEnum.ACTIVE
    ) -> List[User]:
        """获取指定月份生日的用户"""
        query = self.get_query().filter(birth_date__isnull=False)

        if status:
            query = query.filter(status=status)

        return await query.filter(birth_date__month=month).all()

    async def search_users(
            self,
            keyword: Optional[str] = None,
            status: Optional[UserStatusEnum] = None,
            tenant_id: Optional[int] = None,
            role_id: Optional[int] = None,
            offset: int = 0,
            limit: int = 20,
            order_by: str = "-created_at"
    ) -> Tuple[List[User], int]:
        """搜索用户（支持分页、过滤、排序）"""
        query = self.get_query()

        # 状态过滤
        if status:
            query = query.filter(status=status)

        # 租户过滤
        if tenant_id:
            query = query.filter(tenants__id=tenant_id)

        # 角色过滤
        if role_id:
            query = query.filter(roles__id=role_id)

        # 关键词搜索
        if keyword:
            search_q = Q()
            for field in self.default_search_fields:
                search_q |= Q(**{f"{field}__icontains": keyword})
            query = query.filter(search_q)

        # 获取总数
        total = await query.count()

        # 排序和分页
        users = await query.offset(offset).limit(limit).order_by(order_by)

        return list(users), total

    # ========== 角色相关操作方法 ==========

    async def assign_role(
            self,
            user: Union[int, User],
            role: Union[int, Role],
            expires_in_days: Optional[int] = None,
            metadata: Optional[Dict] = None
    ) -> UserRole:
        """给用户分配单个角色"""
        user_obj = await self._get_user_instance(user)
        return await UserRole.grant_role(
            user=user_obj,
            role=role,
            expires_in_days=expires_in_days,
            metadata=metadata
        )

    async def assign_roles(
            self,
            user: Union[int, User],
            roles: List[Union[int, Role]],
            expires_in_days: Optional[int] = None,
            metadata: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """给用户批量分配角色"""
        user_obj = await self._get_user_instance(user)
        return await UserRole.bulk_grant_roles(
            user=user_obj,
            roles=roles,
            expires_in_days=expires_in_days,
            metadata=metadata
        )

    async def revoke_role(
            self,
            user: Union[int, User],
            role: Union[int, Role]
    ) -> bool:
        """撤销用户的单个角色"""
        user_obj = await self._get_user_instance(user)
        return await UserRole.revoke_role(user=user_obj, role=role)

    async def revoke_roles(
            self,
            user: Union[int, User],
            roles: List[Union[int, Role]]
    ) -> int:
        """批量撤销用户的指定角色"""
        user_obj = await self._get_user_instance(user)
        return await UserRole.bulk_revoke_roles(user=user_obj, roles=roles)

    async def revoke_all_roles(
            self,
            user: Union[int, User]
    ) -> int:
        """撤销用户的所有有效角色"""
        user_obj = await self._get_user_instance(user)
        return await UserRole.bulk_revoke_roles(user=user_obj)

    async def get_roles(
            self,
            user: Union[int, User],
            include_expired: bool = False,
            include_revoked: bool = False
    ) -> List[Role]:
        """获取用户的角色列表"""
        user_obj = await self._get_user_instance(user)
        user_roles = await UserRole.get_user_roles(
            user=user_obj,
            include_expired=include_expired,
            include_revoked=include_revoked
        )
        return [ur.role for ur in user_roles]

    async def get_valid_roles(
            self,
            user: Union[int, User]
    ) -> List[Role]:
        """获取用户的有效角色"""
        return await self.get_roles(
            user=user,
            include_expired=False,
            include_revoked=False
        )

    async def has_role(
            self,
            user: Union[int, User],
            role: Union[int, Role, str],
            check_valid: bool = True
    ) -> bool:
        """检查用户是否拥有指定角色"""
        user_obj = await self._get_user_instance(user)
        return await UserRole.has_role(
            user=user_obj,
            role=role,
            check_valid=check_valid
        )

    async def refresh_role_expiry(
            self,
            user: Union[int, User],
            role: Union[int, Role],
            expires_in_days: int
    ) -> bool:
        """刷新角色过期时间"""
        user_obj = await self._get_user_instance(user)
        return await UserRole.refresh_expires_at(
            user=user_obj,
            role=role,
            expires_in_days=expires_in_days
        )

    # ========== 租户相关操作方法 ==========

    async def get_tenants(
            self,
            user: Union[int, User]
    ) -> List[Tenant]:
        """获取用户所属的所有租户"""
        user_obj = await self._get_user_instance(user)
        return await user_obj.tenants.filter(is_deleted=False).all()

    async def get_primary_tenant(
            self,
            user: Union[int, User]
    ) -> Optional[Tenant]:
        """获取用户的主租户"""
        user_obj = await self._get_user_instance(user)
        tenant_user = await TenantUser.objects.filter(
            user=user_obj,
            is_primary=True,
            is_assigned=True,
            is_deleted=False
        ).first()
        return tenant_user.tenant if tenant_user else None

    async def assign_to_tenant(
            self,
            user: Union[int, User],
            tenant: Union[int, Tenant],
            is_primary: bool = False,
            metadata: Optional[Dict] = None
    ) -> TenantUser:
        """将用户分配到租户"""
        user_obj = await self._get_user_instance(user)
        tenant_obj = await self._get_tenant_instance(tenant)

        # 检查是否已存在
        existing = await TenantUser.objects.filter(
            user=user_obj,
            tenant=tenant_obj,
            is_deleted=False
        ).first()

        if existing:
            existing.is_primary = is_primary
            existing.metadata = metadata or existing.metadata
            await existing.save()
            return existing

        # 创建新的租户用户关系
        return await TenantUser.create(
            user=user_obj,
            tenant=tenant_obj,
            is_primary=is_primary,
            metadata=metadata
        )

    # ========== 带租户参数的角色方法 ==========

    async def assign_role_in_tenant(
            self,
            user: Union[int, User],
            role: Union[int, Role],
            tenant: Union[int, Tenant],
            expires_in_days: Optional[int] = None,
            metadata: Optional[Dict] = None
    ) -> UserRole:
        """在指定租户下为用户分配角色"""
        user_obj = await self._get_user_instance(user)
        tenant_obj = await self._get_tenant_instance(tenant)

        # 检查用户是否属于该租户
        if not await TenantUser.has_user(tenant=tenant_obj, user=user_obj, check_valid=True):
            raise ValueError(f"用户[{user_obj.username}]不属于租户[{tenant_obj.code}]")

        # 检查角色是否属于该租户
        role_obj = await Role.objects.get(id=role) if isinstance(role, int) else role
        if role_obj.tenant_id != tenant_obj.id:
            raise ValueError("角色不属于指定租户")

        return await UserRole.grant_role(
            user=user_obj,
            role=role,
            expires_in_days=expires_in_days,
            metadata=metadata
        )

    async def get_roles_in_tenant(
            self,
            user: Union[int, User],
            tenant: Union[int, Tenant],
            include_expired: bool = False,
            include_revoked: bool = False
    ) -> List[Role]:
        """获取用户在指定租户下的角色"""
        user_obj = await self._get_user_instance(user)
        tenant_obj = await self._get_tenant_instance(tenant)

        user_roles = await UserRole.get_user_roles(
            user=user_obj,
            include_expired=include_expired,
            include_revoked=include_revoked,
            tenant_id=tenant_obj.id
        )
        return [ur.role for ur in user_roles]

    async def has_role_in_tenant(
            self,
            user: Union[int, User],
            role: Union[int, Role, str],
            tenant: Union[int, Tenant],
            check_valid: bool = True
    ) -> bool:
        """检查用户在指定租户下是否拥有指定角色"""
        user_obj = await self._get_user_instance(user)
        tenant_obj = await self._get_tenant_instance(tenant)

        return await UserRole.has_role(
            user=user_obj,
            role=role,
            check_valid=check_valid,
            tenant_id=tenant_obj.id
        )

    # ========== 辅助方法 ==========

    async def _get_user_instance(self, user: Union[int, User]) -> User:
        """获取用户实例"""
        if isinstance(user, User):
            return user
        user_obj = await self.get_by_id(user)
        if not user_obj:
            raise ValueError(f"用户ID {user} 不存在")
        return user_obj

    async def _get_tenant_instance(self, tenant: Union[int, Tenant]) -> Tenant:
        """获取租户实例"""
        if isinstance(tenant, Tenant):
            return tenant

        from azer_common.repositories import tenant_repository
        tenant_repo = tenant_repository.TenantRepository()
        tenant_obj = await tenant_repo.get_by_id(tenant)
        if not tenant_obj:
            raise ValueError(f"租户ID {tenant} 不存在")
        return tenant_obj


# 创建全局实例
user_repository = UserRepository()
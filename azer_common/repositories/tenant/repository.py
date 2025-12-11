# azer_common/repositories/tenant/repository.py
from typing import Optional, List, Dict, Any, Tuple

from azer_common.models.role.model import Role
from azer_common.repositories.base import BaseRepository
from azer_common.models.tenant.model import Tenant
from azer_common.models.relations.tenant_user import TenantUser
from azer_common.models.user.model import User
from azer_common.repositories.role.repository import RoleRepository
from azer_common.utils.time import utc_now


class TenantRepository(BaseRepository[Tenant]):
    """租户数据访问层，提供租户相关的数据库操作"""

    def __init__(self):
        super().__init__(Tenant)

    async def get_by_code(self, code: str) -> Optional[Tenant]:
        """
        根据租户编码获取租户信息
        :param code: 租户编码
        :return: 租户实例或None
        """
        return await self.model.filter(code=code, is_deleted=False).first()

    async def check_code_exists(self, code: str, exclude_id: Optional[str] = None) -> bool:
        """
        检查租户编码是否已存在
        :param code: 租户编码
        :param exclude_id: 排除的租户ID（用于更新场景）
        :return: 存在返回True，否则返回False
        """
        query = self.model.filter(code=code, is_deleted=False)
        if exclude_id:
            query = query.exclude(id=exclude_id)
        return await query.exists()

    async def enable_tenant(self, tenant_id: str) -> Optional[Tenant]:
        """
        启用租户
        :param tenant_id: 租户ID
        :return: 启用后的租户实例或None
        """
        tenant = await self.get_by_id(tenant_id)
        if not tenant:
            return None

        await tenant.enable()
        return tenant

    async def disable_tenant(self, tenant_id: str) -> Optional[Tenant]:
        """
        禁用租户
        :param tenant_id: 租户ID
        :return: 禁用后的租户实例或None
        """
        tenant = await self.get_by_id(tenant_id)
        if not tenant:
            return None

        await tenant.disable()
        return tenant

    async def get_enabled_tenants(
            self,
            offset: int = 0,
            limit: int = 20,
            tenant_type: Optional[str] = None
    ) -> Tuple[List[Tenant], int]:
        """
        获取所有启用的租户列表（支持分页和类型过滤）
        :param offset: 分页偏移量
        :param limit: 分页大小
        :param tenant_type: 租户类型过滤（可选）
        :return: 租户列表和总数量
        """
        filters = {"is_enabled": True, "is_deleted": False}
        if tenant_type:
            filters["tenant_type"] = tenant_type

        return await self.filter(
            offset=offset,
            limit=limit,
            order_by="-created_at",
            **filters
        )

    async def get_expired_tenants(self) -> List[Tenant]:
        """
        获取已过期的租户列表
        :return: 过期租户列表
        """
        now = utc_now()
        return await self.model.filter(
            is_enabled=True,
            is_deleted=False,
            expired_at__isnull=False,
            expired_at__lte=now
        ).all()

    async def search_tenants(
            self,
            keyword: str,
            offset: int = 0,
            limit: int = 20
    ) -> Tuple[List[Tenant], int]:
        """
        搜索租户（支持按编码和名称模糊查询）
        :param keyword: 搜索关键词
        :param offset: 分页偏移量
        :param limit: 分页大小
        :return: 租户列表和总数量
        """
        return await self.search(
            keyword=keyword,
            search_fields=["code", "name", "contact"],
            offset=offset,
            limit=limit
        )

    async def add_user_to_tenant(
            self,
            tenant_id: str,
            user_id: str,
            is_primary: bool = False,
            expires_at: Optional[Any] = None,
            metadata: Optional[Dict[str, Any]] = None
    ) -> TenantUser:
        """
        添加用户到租户
        :param tenant_id: 租户ID
        :param user_id: 用户ID
        :param is_primary: 是否为主租户
        :param expires_at: 过期时间
        :param metadata: 元数据
        :return: 创建的租户用户关联实例
        """
        async with self.transaction():
            # 检查租户和用户是否存在
            if not await self.exists(id=tenant_id):
                raise ValueError(f"租户不存在: {tenant_id}")

            from azer_common.repositories.user.repository import UserRepository
            user_repo = UserRepository()
            if not await user_repo.exists(id=user_id):
                raise ValueError(f"用户不存在: {user_id}")

            # 如果设为主租户，先取消该用户的其他主租户关联
            if is_primary:
                await TenantUser.filter(
                    user_id=user_id,
                    is_primary=True,
                    is_deleted=False
                ).update(is_primary=False)

            # 创建或更新租户用户关联
            tenant_user, created = await TenantUser.get_or_create(
                tenant_id=tenant_id,
                user_id=user_id,
                is_deleted=False,
                defaults={
                    "is_primary": is_primary,
                    "is_assigned": True,
                    "expires_at": expires_at,
                    "metadata": metadata
                }
            )

            if not created:
                tenant_user.is_primary = is_primary
                tenant_user.is_assigned = True
                tenant_user.expires_at = expires_at
                if metadata is not None:
                    tenant_user.metadata = metadata
                await tenant_user.save()

            return tenant_user

    async def remove_user_from_tenant(self, tenant_id: str, user_id: str) -> bool:
        """
        从租户移除用户（软删除关联关系）
        :param tenant_id: 租户ID
        :param user_id: 用户ID
        :return: 操作成功返回True，否则返回False
        """
        tenant_user = await TenantUser.filter(
            tenant_id=tenant_id,
            user_id=user_id,
            is_deleted=False
        ).first()

        if not tenant_user:
            return False

        await tenant_user.soft_delete()
        return True

    async def get_tenant_users(
            self,
            tenant_id: str,
            offset: int = 0,
            limit: int = 20
    ) -> Tuple[List[User], int]:
        """
        获取租户下的用户列表
        :param tenant_id: 租户ID
        :param offset: 分页偏移量
        :param limit: 分页大小
        :return: 用户列表和总数量
        """
        tenant = await self.get_by_id(tenant_id)
        if not tenant:
            return [], 0

        query = tenant.users.filter(is_deleted=False).order_by("-created_at")
        total = await query.count()
        users = await query.offset(offset).limit(limit).all()
        return users, total

    async def batch_add_users_to_tenant(
            self,
            tenant_id: str,
            user_data_list: List[Dict[str, Any]]
    ) -> Tuple[int, List[TenantUser]]:
        """
        批量添加用户到租户
        :param tenant_id: 租户ID
        :param user_data_list: 用户数据列表，每个元素包含:
            - user_id: str (必填)
            - is_primary: bool = False
            - expires_at: Optional[datetime] = None
            - metadata: Optional[Dict] = None
        :return: (成功添加数量, 创建的关联实例列表)
        """
        async with self.transaction():
            # 检查租户是否存在
            if not await self.exists(id=tenant_id):
                raise ValueError(f"租户不存在: {tenant_id}")

            # 批量检查用户是否存在
            user_ids = [data.get("user_id") for data in user_data_list if data.get("user_id")]
            existing_users = await self.user_repo.get_by_ids(user_ids)
            existing_user_ids = {user.id for user in existing_users}

            if len(existing_user_ids) != len(user_ids):
                missing_ids = set(user_ids) - existing_user_ids
                raise ValueError(f"部分用户不存在: {missing_ids}")

            created_relations = []
            success_count = 0

            for user_data in user_data_list:
                try:
                    user_id = user_data.get("user_id")
                    if not user_id:
                        continue

                    # 处理主租户冲突
                    if user_data.get("is_primary", False):
                        await TenantUser.filter(
                            user_id=user_id,
                            is_primary=True,
                            is_deleted=False
                        ).update(is_primary=False)

                    # 创建或更新关联
                    tenant_user, created = await TenantUser.get_or_create(
                        tenant_id=tenant_id,
                        user_id=user_id,
                        is_deleted=False,
                        defaults={
                            "is_primary": user_data.get("is_primary", False),
                            "is_assigned": True,
                            "expires_at": user_data.get("expires_at"),
                            "metadata": user_data.get("metadata", {})
                        }
                    )

                    if not created:
                        tenant_user.is_primary = user_data.get("is_primary", False)
                        tenant_user.is_assigned = True
                        tenant_user.expires_at = user_data.get("expires_at")
                        if "metadata" in user_data:
                            tenant_user.metadata = user_data["metadata"]
                        await tenant_user.save()

                    created_relations.append(tenant_user)
                    success_count += 1

                except Exception as e:
                    # 记录错误但继续处理其他用户
                    print(f"添加用户 {user_data.get('user_id')} 到租户失败: {e}")

            return success_count, created_relations

    async def batch_remove_users_from_tenant(
            self,
            tenant_id: str,
            user_ids: List[str]
    ) -> int:
        """
        批量从租户移除用户
        :param tenant_id: 租户ID
        :param user_ids: 用户ID列表
        :return: 成功移除的用户数量
        """
        async with self.transaction():
            # 查询现有的关联
            tenant_users = await TenantUser.filter(
                tenant_id=tenant_id,
                user_id__in=user_ids,
                is_deleted=False
            ).all()

            if not tenant_users:
                return 0

            # 批量软删除关联
            success_count = 0
            for tenant_user in tenant_users:
                try:
                    await tenant_user.soft_delete()
                    success_count += 1
                except Exception as e:
                    print(f"移除用户 {tenant_user.user_id} 失败: {e}")

            return success_count

    # 租户-角色相关方法
    async def create_role_in_tenant(
            self,
            tenant_id: str,
            code: str,
            name: str,
            **kwargs
    ) -> Role:
        """
        在租户下创建角色
        :param tenant_id: 租户ID
        :param code: 角色编码
        :param name: 角色名称
        :param kwargs: 角色其他属性（如description、role_type等）
        :return: 创建的角色实例
        """
        async with self.transaction():
            # 检查租户是否存在
            if not await self.exists(id=tenant_id):
                raise ValueError(f"租户不存在: {tenant_id}")

            role_repo = RoleRepository()
            # 检查角色编码唯一性
            if await role_repo.check_code_exists(code, tenant_id):
                raise ValueError(f"角色编码已存在: {code}")

            # 创建角色（关联当前租户）
            return await role_repo.create(
                tenant_id=tenant_id,
                code=code,
                name=name,
                **kwargs
            )

    async def delete_role_from_tenant(
            self,
            tenant_id: str,
            role_id: str
    ) -> bool:
        """
        从租户中删除角色（软删除）
        :param tenant_id: 租户ID
        :param role_id: 角色ID
        :return: 操作成功返回True
        """
        role_repo = RoleRepository()
        role = await role_repo.get_by_id(role_id)

        if not role or role.tenant_id != tenant_id:
            return False

        # 系统角色禁止删除
        if role.is_system:
            raise ValueError("系统内置角色不允许删除")

        await role.soft_delete()
        return True

    async def update_tenant_role(
            self,
            tenant_id: str,
            role_id: str, **kwargs
    ) -> Optional[Role]:
        """
        更新租户下的角色
        :param tenant_id: 租户ID
        :param role_id: 角色ID
        :param kwargs: 待更新的角色属性
        :return: 更新后的角色实例或None
        """
        role_repo = RoleRepository()
        role = await role_repo.get_by_id(role_id)

        if not role or role.tenant_id != tenant_id:
            return None

        # 若更新编码，需重新检查唯一性
        if "code" in kwargs:
            if await role_repo.check_code_exists(kwargs["code"], tenant_id, role_id):
                raise ValueError(f"角色编码已存在: {kwargs['code']}")

        return await role_repo.update(role_id, **kwargs)

    async def get_tenant_roles(
            self,
            tenant_id: str,
            is_enabled: Optional[bool] = None,
            offset: int = 0,
            limit: int = 20
    ) -> Tuple[List[Role], int]:
        """
        获取租户下的角色列表
        :param tenant_id: 租户ID
        :param is_enabled: 是否启用（None表示不限制）
        :param offset: 分页偏移量
        :param limit: 分页大小
        :return: 角色列表和总数量
        """
        filters = {"tenant_id": tenant_id, "is_deleted": False}
        if is_enabled is not None:
            filters["is_enabled"] = is_enabled

        return await self.filter(
            model=Role,
            offset=offset,
            limit=limit,
            order_by="-created_at",
            **filters
        )

    async def batch_add_roles_to_tenant(
            self,
            tenant_id: str,
            roles_data: List[Dict[str, Any]]
    ) -> List[Role]:
        """
        批量添加角色到租户
        :param tenant_id: 租户ID
        :param roles_data: 角色数据列表（包含code、name等字段）
        :return: 创建的角色列表
        """
        async with self.transaction():
            created_roles = []
            for role_data in roles_data:
                role = await self.create_role_in_tenant(tenant_id, **role_data)
                created_roles.append(role)
            return created_roles

    async def batch_remove_roles_from_tenant(
            self,
            tenant_id: str,
            role_ids: List[str]
    ) -> int:
        """
        批量从租户中删除角色（软删除）
        :param tenant_id: 租户ID
        :param role_ids: 角色ID列表
        :return: 成功删除的数量
        """
        async with self.transaction():
            deleted_count = 0
            for role_id in role_ids:
                if await self.delete_role_from_tenant(tenant_id, role_id):
                    deleted_count += 1
            return deleted_count

    async def search_tenant_roles(
            self,
            tenant_id: str,
            keyword: str,
            offset: int = 0,
            limit: int = 20
    ) -> Tuple[List[Role], int]:
        """
        搜索租户下的角色
        :param tenant_id: 租户ID
        :param keyword: 搜索关键词（匹配code、name）
        :param offset: 分页偏移量
        :param limit: 分页大小
        :return: 角色列表和总数量
        """
        role_repo = RoleRepository()
        return await role_repo.search(
            keyword=keyword,
            search_fields=["code", "name", "description"],
            offset=offset,
            limit=limit,
            tenant_id=tenant_id
        )

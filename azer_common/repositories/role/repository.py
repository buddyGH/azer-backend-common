# azer_common/repositories/role/repository.py
from typing import Optional, List, Any, Tuple
from azer_common.repositories.base import BaseRepository
from azer_common.models.role.model import Role
from azer_common.models.relations.role_permission import RolePermission
from azer_common.models.relations.user_role import UserRole
from azer_common.models.permission.model import Permission
from azer_common.utils.time import utc_now


class RoleRepository(BaseRepository[Role]):
    """角色数据访问层，提供角色相关的数据库操作"""

    def __init__(self):
        super().__init__(Role)

    async def get_by_code(self, code: str, tenant_id: Optional[str] = None) -> Optional[Role]:
        """
        根据角色编码和租户ID获取角色
        :param code: 角色编码
        :param tenant_id: 租户ID（None表示全局角色）
        :return: 角色实例或None
        """
        filters = {"code": code, "is_deleted": False}
        if tenant_id is not None:
            filters["tenant_id"] = tenant_id
        else:
            filters["tenant_id__isnull"] = True
        return await self.model.filter(**filters).first()

    async def check_code_exists(
            self,
            code: str,
            tenant_id: Optional[str] = None,
            exclude_id: Optional[str] = None
    ) -> bool:
        """
        检查角色编码是否已存在（同一租户内唯一）
        :param code: 角色编码
        :param tenant_id: 租户ID
        :param exclude_id: 排除的角色ID（更新场景）
        :return: 存在返回True
        """
        query = self.model.filter(code=code, is_deleted=False)
        if tenant_id is not None:
            query = query.filter(tenant_id=tenant_id)
        else:
            query = query.filter(tenant_id__isnull=True)
        if exclude_id:
            query = query.exclude(id=exclude_id)
        return await query.exists()

    async def get_tenant_roles(
            self,
            tenant_id: Optional[str] = None,
            is_enabled: Optional[bool] = None,
            offset: int = 0,
            limit: int = 20
    ) -> Tuple[List[Role], int]:
        """
        获取租户下的角色列表（支持全局角色）
        :param tenant_id: 租户ID（None查询全局角色）
        :param is_enabled: 是否启用（None表示不限制）
        :param offset: 分页偏移量
        :param limit: 分页大小
        :return: 角色列表和总数量
        """
        filters = {"is_deleted": False}
        if tenant_id is not None:
            filters["tenant_id"] = tenant_id
        else:
            filters["tenant_id__isnull"] = True
        if is_enabled is not None:
            filters["is_enabled"] = is_enabled

        return await self.filter(
            offset=offset,
            limit=limit,
            order_by="-created_at",
            **filters
        )

    async def get_role_permissions(
            self,
            role_id: str,
            is_granted: bool = True
    ) -> List[Permission]:
        """
        获取角色拥有的权限列表
        :param role_id: 角色ID
        :param is_granted: 是否仅查询已授予的权限
        :return: 权限列表
        """
        query = RolePermission.filter(
            role_id=role_id,
            is_deleted=False,
            is_granted=is_granted
        ).select_related("permission")

        role_permissions = await query.all()
        return [rp.permission for rp in role_permissions if rp.permission]

    async def grant_permissions(
            self,
            role_id: str,
            permission_ids: List[str],
            tenant_id: Optional[str] = None,
            effective_from: Optional[Any] = None,
            effective_to: Optional[Any] = None
    ) -> int:
        """
        给角色授予权限
        :param role_id: 角色ID
        :param permission_ids: 权限ID列表
        :param tenant_id: 租户ID（用于权限范围限制）
        :param effective_from: 生效开始时间
        :param effective_to: 生效结束时间
        :return: 授予成功的数量
        """
        if not permission_ids:
            return 0

        async with self.transaction():
            # 检查角色是否存在
            if not await self.exists(id=role_id):
                raise ValueError(f"角色不存在: {role_id}")

            # 批量创建或更新权限关联
            created_count = 0
            for perm_id in permission_ids:
                rp, created = await RolePermission.get_or_create(
                    role_id=role_id,
                    permission_id=perm_id,
                    tenant_id=tenant_id,
                    is_deleted=False,
                    defaults={
                        "is_granted": True,
                        "effective_from": effective_from,
                        "effective_to": effective_to
                    }
                )
                if not created and not rp.is_granted:
                    rp.is_granted = True
                    rp.effective_from = effective_from
                    rp.effective_to = effective_to
                    await rp.save()
                created_count += 1
            return created_count

    async def revoke_permissions(
            self,
            role_id: str,
            permission_ids: List[str],
            tenant_id: Optional[str] = None
    ) -> int:
        """
        撤销角色的权限
        :param role_id: 角色ID
        :param permission_ids: 权限ID列表
        :param tenant_id: 租户ID
        :return: 撤销成功的数量
        """
        if not permission_ids:
            return 0

        query = RolePermission.filter(
            role_id=role_id,
            permission_id__in=permission_ids,
            is_deleted=False,
            is_granted=True
        )
        if tenant_id is not None:
            query = query.filter(tenant_id=tenant_id)
        else:
            query = query.filter(tenant_id__isnull=True)

        # 软删除权限关联（同步标记为未授予）
        rp_list = await query.all()
        for rp in rp_list:
            await rp.soft_delete()
        return len(rp_list)

    async def get_role_users(
            self,
            role_id: str,
            tenant_id: str,
            offset: int = 0,
            limit: int = 20
    ) -> Tuple[List[Any], int]:
        """
        获取拥有该角色的用户列表
        :param role_id: 角色ID
        :param tenant_id: 租户ID
        :param offset: 分页偏移量
        :param limit: 分页大小
        :return: 用户列表和总数量
        """
        query = UserRole.filter(
            role_id=role_id,
            tenant_id=tenant_id,
            is_assigned=True,
            is_deleted=False
        ).select_related("user").order_by("-created_at")

        total = await query.count()
        user_roles = await query.offset(offset).limit(limit).all()
        return [ur.user for ur in user_roles if ur.user], total

    async def assign_users(
            self,
            role_id: str,
            user_ids: List[str],
            tenant_id: str,
            expires_at: Optional[Any] = None
    ) -> int:
        """
        给用户分配角色
        :param role_id: 角色ID
        :param user_ids: 用户ID列表
        :param tenant_id: 租户ID
        :param expires_at: 过期时间
        :return: 分配成功的数量
        """
        if not user_ids:
            return 0

        async with self.transaction():
            # 检查角色和租户是否存在
            if not await self.exists(id=role_id, tenant_id=tenant_id):
                raise ValueError(f"角色在指定租户下不存在: {role_id}@{tenant_id}")

            assigned_count = 0
            for user_id in user_ids:
                ur, created = await UserRole.get_or_create(
                    user_id=user_id,
                    role_id=role_id,
                    tenant_id=tenant_id,
                    is_deleted=False,
                    defaults={
                        "is_assigned": True,
                        "expires_at": expires_at
                    }
                )
                if not created and not ur.is_assigned:
                    ur.is_assigned = True
                    ur.expires_at = expires_at
                    await ur.save()
                assigned_count += 1
            return assigned_count

    async def remove_users(
            self,
            role_id: str,
            user_ids: List[str],
            tenant_id: str
    ) -> int:
        """
        从角色中移除用户
        :param role_id: 角色ID
        :param user_ids: 用户ID列表
        :param tenant_id: 租户ID
        :return: 移除成功的数量
        """
        if not user_ids:
            return 0

        query = UserRole.filter(
            role_id=role_id,
            user_id__in=user_ids,
            tenant_id=tenant_id,
            is_deleted=False
        )

        # 软删除用户角色关联
        ur_list = await query.all()
        for ur in ur_list:
            await ur.soft_delete()
        return len(ur_list)

    async def search_roles(
            self,
            keyword: str,
            tenant_id: Optional[str] = None,
            offset: int = 0,
            limit: int = 20
    ) -> Tuple[List[Role], int]:
        """
        搜索角色（支持按编码和名称模糊查询）
        :param keyword: 搜索关键词
        :param tenant_id: 租户ID（None查询全局角色）
        :param offset: 分页偏移量
        :param limit: 分页大小
        :return: 角色列表和总数量
        """
        filters = {}
        if tenant_id is not None:
            filters["tenant_id"] = tenant_id
        else:
            filters["tenant_id__isnull"] = True

        return await self.search(
            keyword=keyword,
            search_fields=["code", "name", "description"],
            offset=offset,
            limit=limit,
            **filters
        )

    async def delete_role(self, role_id: str) -> bool:
        """
        删除角色（系统角色禁止删除）
        :param role_id: 角色ID
        :return: 操作成功返回True
        """
        role = await self.get_by_id(role_id)
        if not role:
            return False

        if role.is_system:
            raise ValueError("系统内置角色不允许删除")

        # 先删除关联关系
        async with self.transaction():
            # 软删除角色-权限关联
            await RolePermission.filter(role_id=role_id, is_deleted=False).update(
                is_deleted=True,
                is_granted=False,
                deleted_at=utc_now()
            )
            # 软删除用户-角色关联
            await UserRole.filter(role_id=role_id, is_deleted=False).update(
                is_deleted=True,
                is_assigned=False,
                deleted_at=utc_now()
            )
            # 软删除角色本身
            await role.soft_delete()
        return True

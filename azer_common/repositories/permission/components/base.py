# azer_common/repositories/permission/components/base.py
from typing import List, Optional, Tuple
from tortoise.functions import Count
from azer_common.models.permission.model import Permission
from azer_common.models.relations.role_permission import RolePermission
from azer_common.repositories.base_component import BaseComponent
from azer_common.utils.time import utc_now


class PermissionBaseComponent(BaseComponent):
    async def get_by_code(self, code: str, tenant_id: Optional[str] = None) -> Optional[Permission]:
        """
        根据权限编码和租户ID获取权限
        :param code: 权限编码
        :param tenant_id: 租户ID（None表示全局权限）
        :return: 权限实例或None
        """
        filters = {"code": code, "is_deleted": False}
        if tenant_id is not None:
            filters["tenant_id"] = tenant_id
        else:
            filters["tenant_id__isnull"] = True
        return await self.model.filter(**filters).first()

    async def check_code_exists(
        self, code: str, tenant_id: Optional[str] = None, exclude_id: Optional[str] = None
    ) -> bool:
        """
        检查权限编码是否已存在（同一租户内唯一）
        :param code: 权限编码
        :param tenant_id: 租户ID
        :param exclude_id: 排除的权限ID（更新场景）
        :return: 存在返回True
        """
        query = self.model.objects.filter(code=code)
        if tenant_id is not None:
            query = query.filter(tenant_id=tenant_id)
        else:
            query = query.filter(tenant_id__isnull=True)
        if exclude_id:
            query = query.exclude(id=exclude_id)
        return await query.exists()

    async def get_permissions_by_tenant(
        self, tenant_id: Optional[str] = None, is_enabled: Optional[bool] = None, offset: int = 0, limit: int = 20
    ) -> Tuple[List[Permission], int]:
        """
        获取租户下的权限列表（支持全局权限）
        :param tenant_id: 租户ID（None查询全局权限）
        :param is_enabled: 是否启用（None表示不限制）
        :param offset: 分页偏移量
        :param limit: 分页大小
        :return: 权限列表和总数量
        """
        filters = {"is_deleted": False}
        if tenant_id is not None:
            filters["tenant_id"] = tenant_id
        else:
            filters["tenant_id__isnull"] = True
        if is_enabled is not None:
            filters["is_enabled"] = is_enabled

        return await self.filter(offset=offset, limit=limit, order_by="category, module, code", **filters)

    async def get_permissions_by_category(
        self, category: str, tenant_id: Optional[str] = None, is_enabled: bool = True, offset: int = 0, limit: int = 20
    ) -> Tuple[List[Permission], int]:
        """
        按分类获取权限列表
        :param category: 权限分类（如：system、user）
        :param tenant_id: 租户ID（None查询全局权限）
        :param is_enabled: 是否仅查询启用的权限
        :param offset: 分页偏移量
        :param limit: 分页大小
        :return: 权限列表和总数量
        """
        filters = {"category": category, "is_deleted": False, "is_enabled": is_enabled}
        if tenant_id is not None:
            filters["tenant_id"] = tenant_id
        else:
            filters["tenant_id__isnull"] = True

        return await self.filter(offset=offset, limit=limit, order_by="module, code", **filters)

    async def get_permissions_by_module(
        self, module: str, tenant_id: Optional[str] = None, is_enabled: bool = True, offset: int = 0, limit: int = 20
    ) -> Tuple[List[Permission], int]:
        """
        按模块获取权限列表
        :param module: 业务模块名称
        :param tenant_id: 租户ID（None查询全局权限）
        :param is_enabled: 是否仅查询启用的权限
        :param offset: 分页偏移量
        :param limit: 分页大小
        :return: 权限列表和总数量
        """
        if not module:
            raise ValueError("模块名称不能为空")

        filters = {"module": module, "is_deleted": False, "is_enabled": is_enabled}
        if tenant_id is not None:
            filters["tenant_id"] = tenant_id
        else:
            filters["tenant_id__isnull"] = True

        return await self.filter(offset=offset, limit=limit, order_by="category, code", **filters)

    async def get_permissions_by_role(
        self, role_id: str, tenant_id: Optional[str] = None, is_granted: bool = True
    ) -> List[Permission]:
        """
        获取角色拥有的权限列表
        :param role_id: 角色ID
        :param tenant_id: 租户ID（None查询全局权限）
        :param is_granted: 是否仅查询已授予的权限
        :return: 权限列表
        """
        query = RolePermission.objects.filter(role_id=role_id, is_granted=is_granted).select_related("permission")

        if tenant_id is not None:
            query = query.filter(tenant_id=tenant_id)
        else:
            query = query.filter(tenant_id__isnull=True)

        role_permissions = await query.all()
        return [rp.permission for rp in role_permissions if rp.permission]

    async def delete_permission(self, permission_id: str) -> bool:
        """
        删除权限（系统权限禁止删除）
        :param permission_id: 权限ID
        :return: 操作成功返回True
        """
        permission = await self.get_by_id(permission_id)
        if not permission:
            return False

        if permission.is_system:
            raise ValueError("系统内置权限不允许删除")

        # 先删除关联关系
        async with self.transaction():
            # 软删除角色-权限关联
            await RolePermission.objects.filter(permission_id=permission_id).update(
                is_deleted=True, is_granted=False, deleted_at=utc_now()
            )
            # 软删除权限本身
            await permission.soft_delete()
        return True

    async def enable_permission(self, permission_id: str) -> Optional[Permission]:
        """
        启用权限
        :param permission_id: 权限ID
        :return: 启用后的权限实例
        """
        permission = await self.get_by_id(permission_id)
        if not permission:
            return None
        await permission.enable()
        return permission

    async def disable_permission(self, permission_id: str) -> Optional[Permission]:
        """
        禁用权限
        :param permission_id: 权限ID
        :return: 禁用后的权限实例
        """
        permission = await self.get_by_id(permission_id)
        if not permission:
            return None
        await permission.disable()
        return permission

    async def count_by_category(self, tenant_id: Optional[str] = None, is_enabled: bool = True) -> dict:
        """
        统计各分类的权限数量
        :param tenant_id: 租户ID（None表示全局权限）
        :param is_enabled: 是否仅统计启用的权限
        :return: 分类统计字典 {category: count}
        """
        filters = {"is_deleted": False, "is_enabled": is_enabled}
        if tenant_id is not None:
            filters["tenant_id"] = tenant_id
        else:
            filters["tenant_id__isnull"] = True

        result = (
            await self.model.filter(**filters)
            .group_by("category")
            .annotate(count=Count("id"))
            .values("category", "count")
        )

        return {item["category"]: item["count"] for item in result}

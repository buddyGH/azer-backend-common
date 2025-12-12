# azer_common/repositories/tenant/components/role.py
from typing import Optional, List, Dict, Any, Tuple
from tortoise.expressions import Q
from azer_common.models.role.model import Role
from azer_common.repositories.base_component import BaseComponent


class TenantRoleComponent(BaseComponent):

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
            # 1. 检查租户是否存在 (使用传入的 tenant_id)
            if not await self.repository.model.objects.filter(id=tenant_id).exists():
                raise ValueError(f"租户不存在: {tenant_id}")

            # 2. 检查角色编码在租户内的唯一性（排除软删除）
            query = Role.objects.filter(
                code=code,
                tenant_id=tenant_id
            )
            if await query.exists():
                raise ValueError(f"角色编码已存在于当前租户: {code}")

            # 3. 创建角色
            return await Role.create(
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
        # 查找角色，确保它属于指定的租户且未被删除
        role = await Role.objects.filter(
            id=role_id,
            tenant_id=tenant_id
        ).first()

        if not role:
            return False

        # 系统角色禁止删除
        if role.is_system:
            raise ValueError("系统内置角色不允许删除")

        # 执行软删除
        await role.soft_delete()
        return True

    async def update_tenant_role(
            self,
            tenant_id: str,
            role_id: str,
            **kwargs
    ) -> Optional[Role]:
        """
        更新租户下的角色
        :param tenant_id: 租户ID
        :param role_id: 角色ID
        :param kwargs: 待更新的角色属性
        :return: 更新后的角色实例或None
        """
        # 查找角色，确保它属于指定的租户且未被删除
        role = await Role.objects.filter(
            id=role_id,
            tenant_id=tenant_id
        ).first()

        if not role:
            return None

        # 若要更新编码，检查新编码在租户内的唯一性（排除自身和软删除记录）
        if "code" in kwargs:
            new_code = kwargs["code"]
            exists = await Role.objects.filter(
                code=new_code,
                tenant_id=tenant_id
            ).exclude(id=role_id).exists()
            if exists:
                raise ValueError(f"角色编码已存在于当前租户: {new_code}")

        # 更新字段
        for key, value in kwargs.items():
            if hasattr(role, key):
                setattr(role, key, value)

        # 触发模型的验证逻辑
        await role.validate()
        await role.save()
        return role

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
        query = Role.objects.filter(tenant_id=tenant_id)

        if is_enabled is not None:
            query = query.filter(is_enabled=is_enabled)

        total = await query.count()
        roles = await query.offset(offset).limit(limit).order_by("-created_at")
        return list(roles), total

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
                # 复用 create_role_in_tenant 方法，它内部会检查租户和编码唯一性
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
        :param keyword: 搜索关键词（匹配code、name、description）
        :param offset: 分页偏移量
        :param limit: 分页大小
        :return: 角色列表和总数量
        """
        if not keyword.strip():
            # 如果关键词为空，返回普通分页结果
            return await self.get_tenant_roles(tenant_id, offset=offset, limit=limit)

        # 构建包含关键词搜索的查询
        query = Role.objects.filter(tenant_id=tenant_id).filter(
            Q(code__icontains=keyword) |
            Q(name__icontains=keyword) |
            Q(description__icontains=keyword)
        )

        total = await query.count()
        roles = await query.offset(offset).limit(limit).order_by("-created_at")
        return list(roles), total

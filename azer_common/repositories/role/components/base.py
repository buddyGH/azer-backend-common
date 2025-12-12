# azer_common/repositories/role/components/base.py
from typing import List, Optional, Tuple
from azer_common.models.relations.role_permission import RolePermission
from azer_common.models.relations.user_role import UserRole
from azer_common.models.role.model import Role
from azer_common.repositories.base_component import BaseComponent
from azer_common.utils.time import utc_now


class RoleBaseComponent(BaseComponent):
    """角色组件基础组件"""

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
        self, code: str, tenant_id: Optional[str] = None, exclude_id: Optional[str] = None
    ) -> bool:
        """
        检查角色编码是否已存在（同一租户内唯一）
        :param code: 角色编码
        :param tenant_id: 租户ID
        :param exclude_id: 排除的角色ID（更新场景）
        :return: 存在返回True
        """
        query = self.query
        if tenant_id is not None:
            query = query.filter(tenant_id=tenant_id)
        else:
            query = query.filter(tenant_id__isnull=True)
        if exclude_id:
            query = query.exclude(id=exclude_id)
        return await query.exists()

    async def enable_role(self, role_id: str) -> Optional[Role]:
        """
        启用角色
        :param role_id: 角色ID
        :return: 启用后的角色实例
        """
        if not role_id:
            raise ValueError("角色ID不能为空")

        role = await self.get_by_id(role_id)
        if not role:
            return None

        # 启用角色的同时，可能需要递归启用其所有子角色（可选）
        # 这里仅启用当前角色，子角色由业务层决定
        await role.enable()
        return role

    async def disable_role(self, role_id: str) -> Optional[Role]:
        """
        禁用角色
        :param role_id: 角色ID
        :return: 禁用后的角色实例
        """
        if not role_id:
            raise ValueError("角色ID不能为空")

        role = await self.get_by_id(role_id)
        if not role:
            return None

        # 禁用角色时，可能需要考虑是否同步禁用其权限关联
        # 这里仅禁用当前角色
        await role.disable()
        return role

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
            await RolePermission.objects.filter(role_id=role_id).update(
                is_deleted=True, is_granted=False, deleted_at=utc_now()
            )
            # 软删除用户-角色关联
            await UserRole.objects.filter(role_id=role_id).update(
                is_deleted=True, is_assigned=False, deleted_at=utc_now()
            )
            # 软删除角色本身
            await role.soft_delete()
        return True

    async def get_default_roles(self, tenant_id: str) -> List[Role]:
        """
        获取租户下的默认角色（新用户自动分配）
        :param tenant_id: 租户ID
        :return: 默认角色列表
        """
        if not tenant_id:
            raise ValueError("租户ID不能为空")

        return (
            await self.model.objects.filter(tenant_id=tenant_id, is_default=True, is_enabled=True)
            .order_by("level desc")
            .all()
        )

    async def get_system_roles(self, tenant_id: str) -> List[Role]:
        """
        获取租户下的系统内置角色
        :param tenant_id: 租户ID
        :return: 系统角色列表
        """
        if not tenant_id:
            raise ValueError("租户ID不能为空")

        return await self.model.objects.filter(tenant_id=tenant_id, is_system=True).order_by("level desc").all()

    async def get_roles_by_tenant(
        self, tenant_id: Optional[str] = None, is_enabled: Optional[bool] = None, offset: int = 0, limit: int = 20
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

        return await self.filter(offset=offset, limit=limit, order_by="-created_at", **filters)

    async def get_roles_by_type(
        self, role_type: str, tenant_id: str, is_enabled: bool = True, offset: int = 0, limit: int = 20
    ) -> Tuple[List[Role], int]:
        """
        按角色类型获取角色列表
        :param role_type: 角色类型
        :param tenant_id: 租户ID
        :param is_enabled: 是否仅查询启用的角色
        :param offset: 分页偏移量
        :param limit: 分页大小
        :return: 角色列表和总数量
        """
        if not role_type:
            raise ValueError("角色类型不能为空")
        if not tenant_id:
            raise ValueError("租户ID不能为空")

        filters = {"role_type": role_type, "tenant_id": tenant_id, "is_deleted": False, "is_enabled": is_enabled}

        return await self.filter(offset=offset, limit=limit, order_by="level desc, created_at", **filters)

    async def get_roles_by_level(
        self, min_level: int, max_level: Optional[int] = None, tenant_id: str = None, is_enabled: bool = True
    ) -> List[Role]:
        """
        按角色等级范围获取角色列表
        :param min_level: 最小等级（包含）
        :param max_level: 最大等级（包含，None表示不限制）
        :param tenant_id: 租户ID（None表示不限制租户）
        :param is_enabled: 是否仅查询启用的角色
        :return: 角色列表
        """
        query = self.model.objects.filter(is_enabled=is_enabled, level__gte=min_level)

        if max_level is not None:
            query = query.filter(level__lte=max_level)

        if tenant_id is not None:
            query = query.filter(tenant_id=tenant_id)

        return await query.order_by("level", "created_at").all()

    async def get_children_roles(
        self, parent_id: str, tenant_id: str, include_self: bool = False, is_enabled: bool = True
    ) -> List[Role]:
        """
        获取角色的子角色列表（用于权限继承）
        :param parent_id: 父角色ID
        :param tenant_id: 租户ID
        :param include_self: 是否包含自身
        :param is_enabled: 是否仅查询启用的角色
        :return: 子角色列表
        """
        if not parent_id:
            raise ValueError("父角色ID不能为空")
        if not tenant_id:
            raise ValueError("租户ID不能为空")

        # 获取直接子角色
        query = self.model.objects.filter(tenant_id=tenant_id, parent_id=parent_id, is_enabled=is_enabled)

        if include_self:
            # 如果需要包含自身，递归获取自身
            role = await self.get_by_id(parent_id)
            if role:
                result = [role]
                children = await query.all()
                result.extend(children)
                return result

        return await query.order_by("level", "created_at").all()

    async def update_role_parent(self, role_id: str, parent_id: Optional[str]) -> Optional[Role]:
        """
        更新角色的父角色（用于调整继承关系）
        :param role_id: 角色ID
        :param parent_id: 新的父角色ID（None表示移除父角色）
        :return: 更新后的角色实例
        """
        if not role_id:
            raise ValueError("角色ID不能为空")

        role = await self.get_by_id(role_id)
        if not role:
            return None

        # 检查循环引用
        if parent_id:
            if parent_id == role_id:
                raise ValueError("角色不能设置自身为父角色")

            # 检查是否形成循环引用（A->B->C->A）
            current = parent_id
            visited = {role_id}
            while current:
                if current in visited:
                    raise ValueError("检测到循环引用，无法设置父角色")

                parent_role = await self.get_by_id(id=current)

                if not parent_role or not parent_role.parent_id:
                    break

                visited.add(current)
                current = parent_role.parent_id

        # 更新父角色
        role.parent_id = parent_id
        await role.save()
        return role

    async def get_role_tree(
        self, tenant_id: str, max_depth: Optional[int] = None, is_enabled: bool = True
    ) -> List[Role]:
        """
        获取角色树形结构（包含父子关系）
        :param tenant_id: 租户ID
        :param max_depth: 最大深度（None表示不限制）
        :param is_enabled: 是否仅查询启用的角色
        :return: 角色列表（需要业务层组装成树）
        """
        if not tenant_id:
            raise ValueError("租户ID不能为空")

        filters = {"tenant_id": tenant_id, "is_deleted": False, "is_enabled": is_enabled}

        # 获取所有符合条件的角色
        roles = await self.model.filter(**filters).order_by("level", "created_at").all()

        # 如果指定了最大深度，过滤掉超过深度的角色
        if max_depth is not None:
            roles_by_id = {role.id: role for role in roles}
            filtered_roles = []

            def calculate_depth(role_id, current_depth=0):
                if current_depth > max_depth:
                    return False
                role = roles_by_id.get(role_id)
                if not role:
                    return True
                if role.parent_id:
                    return calculate_depth(role.parent_id, current_depth + 1)
                return True

            for role in roles:
                if calculate_depth(role.id):
                    filtered_roles.append(role)

            return filtered_roles

        return roles

# azer_common/repositories/role/components/permission.py
from typing import List, Optional, Tuple
from tortoise.expressions import Q
from azer_common.models.permission.model import Permission
from azer_common.models.relations.role_permission import RolePermission
from azer_common.models.role.model import Role
from azer_common.repositories.base_component import BaseComponent
from azer_common.utils.time import utc_now


class RolePermissionComponent(BaseComponent):

    async def get_role_permissions(
        self,
        role_id: str,
        include_inherited: bool = False,
        only_enabled: bool = True,
        only_granted: bool = True,
        include_expired: bool = False,
    ) -> List[Permission]:
        """
        获取角色的权限列表（支持继承查询）
        :param role_id: 角色ID
        :param include_inherited: 是否包含继承的权限
        :param only_enabled: 是否只包含启用的权限
        :param only_granted: 是否只包含已授予的权限
        :param include_expired: 是否包含过期的权限
        :return: 权限列表
        """
        if not role_id:
            raise ValueError("角色ID不能为空")

        # 获取角色信息

        role = await self.get_by_id(id=role_id)
        if not role:
            return []

        # 直接权限
        direct_permissions = await self._get_direct_role_permissions(
            role_id=role_id, only_enabled=only_enabled, only_granted=only_granted, include_expired=include_expired
        )

        if not include_inherited:
            return direct_permissions

        # 获取继承的权限
        inherited_permissions = await self._get_inherited_permissions(
            role=role, only_enabled=only_enabled, only_granted=only_granted, include_expired=include_expired
        )

        # 合并权限，去重（继承的优先级更高）
        permission_map = {p.id: p for p in inherited_permissions}
        for perm in direct_permissions:
            permission_map[perm.id] = perm

        return list(permission_map.values())

    # ========== 角色权限管理方法 ==========

    async def grant_permission_to_role(
        self,
        role_id: str,
        permission_id: str,
        effective_from: Optional[str] = None,
        effective_to: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> RolePermission:
        """
        为角色授予单个权限
        :param role_id: 角色ID
        :param permission_id: 权限ID
        :param effective_from: 生效开始时间
        :param effective_to: 生效结束时间
        :param metadata: 扩展元数据
        :return: 角色权限关联实例
        """
        if not role_id or not permission_id:
            raise ValueError("角色ID和权限ID不能为空")

        # 检查角色和权限是否存在且属于同一租户
        role = await self.get_by_id(id=role_id)
        if not role:
            raise ValueError(f"角色不存在: {role_id}")

        permission = await Permission.objects.filter(id=permission_id).first()
        if not permission:
            raise ValueError(f"权限不存在: {permission_id}")

        # 检查租户一致性（全局权限除外）
        if permission.tenant_id is not None and role.tenant_id != permission.tenant_id:
            raise ValueError("角色和权限必须属于同一租户")

        async with self.transaction:
            # 检查是否已存在关联
            existing = await RolePermission.objects.filter(
                role_id=role_id,
                permission_id=permission_id,
            ).first()

            if existing:
                # 更新现有关联
                existing.is_granted = True
                existing.effective_from = effective_from
                existing.effective_to = effective_to
                if metadata is not None:
                    existing.metadata = metadata
                await existing.save()
                return existing
            else:
                # 创建新关联
                role_permission = RolePermission(
                    role_id=role_id,
                    permission_id=permission_id,
                    tenant_id=role.tenant_id,
                    is_granted=True,
                    effective_from=effective_from,
                    effective_to=effective_to,
                    metadata=metadata,
                )
                await role_permission.save()
                return role_permission

    async def batch_grant_permissions_to_role(
        self,
        role_id: str,
        permission_ids: List[str],
        effective_from: Optional[str] = None,
        effective_to: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> List[RolePermission]:
        """
        为角色批量授予权限
        :param role_id: 角色ID
        :param permission_ids: 权限ID列表
        :param effective_from: 生效开始时间
        :param effective_to: 生效结束时间
        :param metadata: 扩展元数据
        :return: 创建/更新的角色权限关联列表
        """
        if not role_id:
            raise ValueError("角色ID不能为空")
        if not permission_ids:
            return []

        role = await self.get_by_id(id=role_id)
        if not role:
            raise ValueError(f"角色不存在: {role_id}")

        results = []
        async with self.transaction:
            for permission_id in permission_ids:
                try:
                    role_permission = await self.grant_permission_to_role(
                        role_id=role_id,
                        permission_id=permission_id,
                        effective_from=effective_from,
                        effective_to=effective_to,
                        metadata=metadata,
                    )
                    results.append(role_permission)
                except ValueError as e:
                    # 记录错误但继续处理其他权限
                    # 实际应用中可能需要更复杂的错误处理策略
                    print(f"授予权限失败 {permission_id}: {str(e)}")

        return results

    async def revoke_permission_from_role(self, role_id: str, permission_id: str, soft_delete: bool = True) -> bool:
        """
        从角色撤销单个权限
        :param role_id: 角色ID
        :param permission_id: 权限ID
        :param soft_delete: 是否软删除（True: 标记删除, False: 物理删除）
        :return: 操作是否成功
        """
        if not role_id or not permission_id:
            raise ValueError("角色ID和权限ID不能为空")

        async with self.transaction:
            # 查找关联
            role_permission = await RolePermission.objects.filter(role_id=role_id, permission_id=permission_id).first()

            if not role_permission:
                return False

            if soft_delete:
                # 软删除：标记为未授予且删除
                role_permission.is_granted = False
                role_permission.is_deleted = True
                await role_permission.save()
            else:
                # 物理删除
                await role_permission.delete()

            return True

    async def batch_revoke_permissions_from_role(
        self, role_id: str, permission_ids: List[str], soft_delete: bool = True
    ) -> int:
        """
        从角色批量撤销权限
        :param role_id: 角色ID
        :param permission_ids: 权限ID列表
        :param soft_delete: 是否软删除
        :return: 成功撤销的权限数量
        """
        if not role_id:
            raise ValueError("角色ID不能为空")
        if not permission_ids:
            return 0

        async with self.transaction:
            if soft_delete:
                # 批量软删除
                result = await RolePermission.objects.filter(
                    role_id=role_id,
                    permission_id__in=permission_ids,
                ).update(is_granted=False, is_deleted=True, deleted_at=utc_now())
            else:
                # 批量物理删除
                result = await RolePermission.filter(role_id=role_id, permission_id__in=permission_ids).delete()

        return result if isinstance(result, int) else 0

    async def update_role_permission(
        self,
        role_id: str,
        permission_id: str,
        is_granted: Optional[bool] = None,
        effective_from: Optional[str] = None,
        effective_to: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> Optional[RolePermission]:
        """
        更新角色权限关联信息
        :param role_id: 角色ID
        :param permission_id: 权限ID
        :param is_granted: 是否授予
        :param effective_from: 生效开始时间
        :param effective_to: 生效结束时间
        :param metadata: 扩展元数据
        :return: 更新后的关联实例
        """
        if not role_id or not permission_id:
            raise ValueError("角色ID和权限ID不能为空")

        async with self.transaction:
            role_permission = await RolePermission.objects.filter(role_id=role_id, permission_id=permission_id).first()

            if not role_permission:
                return None

            # 更新字段
            if is_granted is not None:
                role_permission.is_granted = is_granted
            if effective_from is not None:
                role_permission.effective_from = effective_from
            if effective_to is not None:
                role_permission.effective_to = effective_to
            if metadata is not None:
                role_permission.metadata = metadata

            await role_permission.save()
            return role_permission

    async def _get_direct_role_permissions(
        self, role_id: str, only_enabled: bool = True, only_granted: bool = True, include_expired: bool = False
    ) -> List[Permission]:
        """获取角色直接关联的权限"""
        query = RolePermission.objects.filter(role_id=role_id).select_related("permission")

        if only_granted:
            query = query.filter(is_granted=True)

        if not include_expired:
            # 过滤已过期的权限
            now = utc_now()
            query = query.filter(Q(effective_to__isnull=True) | Q(effective_to__gte=now))

            role_permissions = await query.all()

            # 过滤权限状态
            permissions = []
            for rp in role_permissions:
                if rp.permission and (not only_enabled or rp.permission.is_enabled):
                    permissions.append(rp.permission)

            return permissions
        return None

    async def _get_inherited_permissions(
        self,
        role: Role,
        only_enabled: bool = True,
        only_granted: bool = True,
        include_expired: bool = False,
        visited: Optional[set] = None,
    ) -> List[Permission]:
        """递归获取继承的权限（防止循环引用）"""
        if visited is None:
            visited = set()

        if role.id in visited:
            return []  # 防止循环引用

        visited.add(role.id)

        # 如果没有父角色，返回空
        if not role.parent_id:
            return []

        # 获取父角色权限
        parent_role = await self.model.objects.filter(
            id=role.parent_id, is_enabled=True  # 父角色必须启用才能继承
        ).first()

        if not parent_role:
            return []

        # 获取父角色的直接权限
        parent_direct = await self._get_direct_role_permissions(
            role_id=parent_role.id,
            only_enabled=only_enabled,
            only_granted=only_granted,
            include_expired=include_expired,
        )

        # 递归获取父角色继承的权限
        parent_inherited = await self._get_inherited_permissions(
            role=parent_role,
            only_enabled=only_enabled,
            only_granted=only_granted,
            include_expired=include_expired,
            visited=visited,
        )

        # 合并父角色的权限
        all_parent_permissions = parent_direct + parent_inherited

        # 根据角色等级处理权限继承：高等级角色可以继承低等级角色的权限
        # 这里假设等级数字越大权限越高，可以根据业务需求调整
        if role.level >= parent_role.level:
            return all_parent_permissions
        else:
            # 如果子角色等级低于父角色，可能需要过滤某些权限
            # 这里返回所有，实际业务可能需要更复杂的逻辑
            return all_parent_permissions

    async def sync_role_permissions(
        self,
        role_id: str,
        permission_ids: List[str],
        effective_from: Optional[str] = None,
        effective_to: Optional[str] = None,
    ) -> Tuple[List[str], List[str], List[str]]:
        """
        同步角色的权限列表（全量更新）
        :param role_id: 角色ID
        :param permission_ids: 新的权限ID列表
        :param effective_from: 生效开始时间
        :param effective_to: 生效结束时间
        :return: (新增的权限ID列表, 删除的权限ID列表, 保留的权限ID列表)
        """
        if not role_id:
            raise ValueError("角色ID不能为空")

        # 获取现有权限
        existing_permissions = await RolePermission.objects.filter(role_id=role_id, is_granted=True).all()

        existing_ids = {rp.permission_id for rp in existing_permissions}
        new_ids = set(permission_ids)

        # 计算差异
        to_add = new_ids - existing_ids
        to_remove = existing_ids - new_ids
        to_keep = existing_ids & new_ids

        async with self.transaction:
            # 删除不再需要的权限
            if to_remove:
                await RolePermission.filter(role_id=role_id, permission_id__in=list(to_remove)).update(
                    is_granted=False, is_deleted=True, deleted_at=utc_now()
                )

            # 添加新权限
            added_ids = []
            for permission_id in to_add:
                try:
                    await self.grant_permission_to_role(
                        role_id=role_id,
                        permission_id=permission_id,
                        effective_from=effective_from,
                        effective_to=effective_to,
                    )
                    added_ids.append(permission_id)
                except Exception as e:
                    print(f"添加权限失败 {permission_id}: {str(e)}")

            # 更新保留权限的生效时间（如果需要）
            if effective_from is not None or effective_to is not None:
                for rp in existing_permissions:
                    if rp.permission_id in to_keep:
                        if effective_from is not None:
                            rp.effective_from = effective_from
                        if effective_to is not None:
                            rp.effective_to = effective_to
                        await rp.save()

        return list(to_add), list(to_remove), list(to_keep)

    async def check_role_has_permission(
        self, role_id: str, permission_code: str, include_inherited: bool = True
    ) -> bool:
        """
        检查角色是否拥有指定权限（支持继承检查）
        :param role_id: 角色ID
        :param permission_code: 权限编码
        :param include_inherited: 是否包含继承的权限
        :return: 是否拥有该权限
        """
        if not role_id or not permission_code:
            return False

        # 获取角色的所有权限
        permissions = await self.get_role_permissions(
            role_id=role_id,
            include_inherited=include_inherited,
            only_enabled=True,
            only_granted=True,
            include_expired=False,
        )

        # 检查是否包含指定权限
        for perm in permissions:
            if perm.code == permission_code:
                return True

        return False

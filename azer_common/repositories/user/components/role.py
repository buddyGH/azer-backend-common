# azer_common/repositories/user/components/user_role.py
from typing import Any, Dict, List, Optional, Tuple
from azer_common.models.relations.tenant_user import TenantUser
from azer_common.models.relations.user_role import UserRole
from azer_common.models.role.model import Role
from azer_common.repositories.base_component import BaseComponent
from azer_common.utils.time import utc_now


class UserRoleComponent(BaseComponent):
    """用户角色管理组件"""

    async def get_user_roles(
        self, user_id: str, tenant_id: str, is_valid: bool = True, offset: int = 0, limit: int = 20
    ) -> Tuple[List[Role], int]:
        """
        获取用户在指定租户下的角色列表
        :param user_id: 用户ID
        :param tenant_id: 租户ID
        :param is_valid: 是否仅返回有效角色（已分配+未过期+未软删除）
        :param offset: 分页偏移量
        :param limit: 分页大小
        :return: 角色列表、总数量
        """
        # 构建基础查询
        query = UserRole.objects.filter(
            user_id=user_id,
            tenant_id=tenant_id,
        )

        # 过滤有效角色关联
        if is_valid:
            query = query.filter(is_assigned=True).exclude(expires_at__lte=utc_now())

        # 关联角色数据并分页
        query = query.select_related("role").order_by("-created_at")
        total = await query.count()
        user_roles = await query.offset(offset).limit(limit).all()

        # 提取有效角色（过滤已禁用/已删除的角色）
        roles = []
        for ur in user_roles:
            role = ur.role
            if role and not role.is_deleted and role.is_enabled:
                roles.append(role)

        return roles, total

    async def assign_role_to_user(
        self,
        user_id: str,
        role_id: str,
        tenant_id: str,
        expires_at: Optional[Any] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> UserRole:
        """
        为用户分配指定租户下的角色
        :param user_id: 用户ID
        :param role_id: 角色ID
        :param tenant_id: 租户ID（需与角色所属租户一致）
        :param expires_at: 角色关联过期时间（None表示永久）
        :param metadata: 扩展元数据
        :return: 创建/更新的用户角色关联实例
        """
        async with self.transaction:
            # 1. 基础校验
            if not await self.exists(id=user_id):
                raise ValueError(f"用户不存在: {user_id}")

            # 2. 校验角色有效性及租户一致性
            role = await Role.objects.filter(id=role_id, tenant_id=tenant_id, is_enabled=True).first()
            if not role:
                raise ValueError(f"租户{tenant_id}下的角色{role_id}不存在或已禁用")

            # 3. 校验用户-租户关联有效性
            tenant_user = await TenantUser.objects.filter(
                user_id=user_id, tenant_id=tenant_id, is_assigned=True
            ).first()
            if not tenant_user:
                raise ValueError(f"用户{user_id}未关联到租户{tenant_id}")

            # 4. 创建/更新角色关联
            user_role, created = await UserRole.objects.get_or_create(
                user_id=user_id,
                role_id=role_id,
                tenant_id=tenant_id,
                defaults={"is_assigned": True, "expires_at": expires_at, "metadata": metadata or {}},
            )

            if not created:
                user_role.is_assigned = True
                user_role.expires_at = expires_at
                if metadata is not None:
                    user_role.metadata = metadata
                await user_role.save()

            return user_role

    async def revoke_role_from_user(self, user_id: str, role_id: str, tenant_id: str, soft_delete: bool = True) -> bool:
        """
        撤销用户在指定租户下的角色
        :param user_id: 用户ID
        :param role_id: 角色ID
        :param tenant_id: 租户ID
        :param soft_delete: 是否软删除（True: 标记为未分配，False: 物理删除）
        :return: 操作成功返回True
        """
        async with self.transaction:
            user_role = await UserRole.objects.filter(
                user_id=user_id,
                role_id=role_id,
                tenant_id=tenant_id,
            ).first()

            if not user_role:
                return False

            if soft_delete:
                # 软删除：标记为未分配+删除
                user_role.is_assigned = False
                user_role.is_deleted = True
                await user_role.save()
            else:
                # 物理删除
                await user_role.delete()

            return True

    async def batch_assign_roles(
        self, user_id: str, tenant_id: str, role_data_list: List[Dict[str, Any]]
    ) -> Tuple[int, List[UserRole]]:
        """
        批量为用户分配多个租户下的角色（单用户+单租户+多角色）
        :param user_id: 用户ID
        :param tenant_id: 租户ID
        :param role_data_list: 角色数据列表，每个元素包含:
            - role_id: str (必填)
            - expires_at: Optional[datetime] = None
            - metadata: Optional[Dict] = None
        :return: (成功分配数量, 创建/更新的角色关联列表)
        """
        async with self.transaction:
            # 1. 基础校验
            if not await self.exists(id=user_id):
                raise ValueError(f"用户不存在: {user_id}")

            # 2. 校验用户-租户关联
            tenant_user = await TenantUser.objects.filter(
                user_id=user_id, tenant_id=tenant_id, is_assigned=True
            ).first()
            if not tenant_user:
                raise ValueError(f"用户{user_id}未关联到租户{tenant_id}")

            # 3. 批量校验角色有效性
            role_ids = [data.get("role_id") for data in role_data_list if data.get("role_id")]
            valid_roles = await Role.objects.filter(id__in=role_ids, tenant_id=tenant_id, is_enabled=True).values_list(
                "id", flat=True
            )
            valid_role_ids = set(valid_roles)

            # 4. 批量分配角色
            success_count = 0
            created_relations = []

            for role_data in role_data_list:
                role_id = role_data.get("role_id")
                if not role_id or role_id not in valid_role_ids:
                    continue

                try:
                    user_role = await self.assign_role_to_user(
                        user_id=user_id,
                        role_id=role_id,
                        tenant_id=tenant_id,
                        expires_at=role_data.get("expires_at"),
                        metadata=role_data.get("metadata"),
                    )
                    created_relations.append(user_role)
                    success_count += 1
                except Exception as e:
                    # 记录错误但继续处理其他角色
                    print(f"分配角色{role_id}失败: {e}")

            return success_count, created_relations

    async def batch_revoke_roles(
        self, user_id: str, tenant_id: str, role_ids: List[str], soft_delete: bool = True
    ) -> int:
        """
        批量撤销用户在指定租户下的角色
        :param user_id: 用户ID
        :param tenant_id: 租户ID
        :param role_ids: 角色ID列表
        :param soft_delete: 是否软删除
        :return: 成功撤销的角色数量
        """
        if not role_ids:
            return 0

        async with self.transaction:
            if soft_delete:
                # 批量软删除
                result = await UserRole.objects.filter(
                    user_id=user_id,
                    tenant_id=tenant_id,
                    role_id__in=role_ids,
                ).update(is_assigned=False, is_deleted=True, deleted_at=utc_now())
            else:
                # 批量物理删除
                result = await UserRole.filter(user_id=user_id, tenant_id=tenant_id, role_id__in=role_ids).delete()

            return result if isinstance(result, int) else 0

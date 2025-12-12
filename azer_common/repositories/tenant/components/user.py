# azer_common/repositories/tenant/components/user.py
from typing import Any, Dict, List, Optional, Tuple
from azer_common.models.relations.tenant_user import TenantUser
from azer_common.models.user.model import User
from azer_common.repositories.base_component import BaseComponent


class TenantUserComponent(BaseComponent):

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
            # 1. 检查租户和用户是否存在（使用基础查询，自动过滤软删除）
            tenant_exists = await self.repository.exists(id=tenant_id)
            if not tenant_exists:
                raise ValueError(f"租户不存在: {tenant_id}")

            user_exists = await User.objects.filter(id=user_id).exists()
            if not user_exists:
                raise ValueError(f"用户不存在: {user_id}")

            # 2. 如果设为主租户，先取消该用户的其他主租户关联
            if is_primary:
                await TenantUser.objects.filter(
                    user_id=user_id,
                    is_primary=True
                ).update(is_primary=False)

            # 3. 创建或更新租户用户关联
            # 注意：使用 get_or_create 时，默认查询会过滤 is_deleted=False 的记录
            # 但我们要检查所有记录（包括软删除的）
            existing_relation = await TenantUser.filter(
                tenant_id=tenant_id,
                user_id=user_id
            ).first()

            if existing_relation:
                # 如果是软删除的记录，恢复它
                if existing_relation.is_deleted:
                    existing_relation.is_deleted = False
                    existing_relation.deleted_at = None

                # 更新字段
                existing_relation.is_primary = is_primary
                existing_relation.is_assigned = True
                existing_relation.expires_at = expires_at
                if metadata is not None:
                    existing_relation.metadata = metadata

                await existing_relation.save()
                return existing_relation
            else:
                # 创建新的关联
                return await TenantUser.create(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    is_primary=is_primary,
                    is_assigned=True,
                    expires_at=expires_at,
                    metadata=metadata or {}
                )

    async def remove_user_from_tenant(self, tenant_id: str, user_id: str) -> bool:
        """
        从租户移除用户（软删除关联关系）
        :param tenant_id: 租户ID
        :param user_id: 用户ID
        :return: 操作成功返回True，否则返回False
        """
        tenant_user = await TenantUser.objects.filter(
            tenant_id=tenant_id,
            user_id=user_id
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
        # 1. 检查租户是否存在
        if not await self.repository.exists(id=tenant_id):
            return [], 0

        # 2. 通过关联表查询用户
        # 先查询有效的关联记录
        tenant_users_query = TenantUser.objects.filter(
            tenant_id=tenant_id,
            is_assigned=True
        )

        # 获取关联记录总数
        total = await tenant_users_query.count()

        # 获取用户ID列表
        user_ids = await tenant_users_query.offset(offset).limit(limit).values_list('user_id', flat=True)

        if not user_ids:
            return [], total

        # 查询用户详情
        users = await User.objects.filter(id__in=user_ids).order_by("-created_at").all()

        return list(users), total

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
            # 1. 检查租户是否存在
            if not await self.repository.exists(id=tenant_id):
                raise ValueError(f"租户不存在: {tenant_id}")

            # 2. 提取所有用户ID并检查存在性
            user_ids = [data.get("user_id") for data in user_data_list if data.get("user_id")]
            if not user_ids:
                return 0, []

            existing_user_ids = await User.objects.filter(id__in=user_ids).values_list('id', flat=True)

            existing_user_set = set(existing_user_ids)

            # 检查是否有不存在的用户
            if len(existing_user_set) != len(set(user_ids)):
                missing_ids = set(user_ids) - existing_user_set
                raise ValueError(f"部分用户不存在: {missing_ids}")

            # 3. 预先处理所有需要设为主租户的用户
            primary_user_ids = [
                data.get("user_id") for data in user_data_list
                if data.get("user_id") and data.get("is_primary", False)
            ]

            if primary_user_ids:
                await TenantUser.objects.filter(
                    user_id__in=primary_user_ids,
                    is_primary=True
                ).update(is_primary=False)

            # 4. 批量处理用户关联
            created_relations = []
            success_count = 0

            for user_data in user_data_list:
                try:
                    user_id = user_data.get("user_id")
                    if not user_id:
                        continue

                    # 检查是否已存在关联
                    existing_relation = await TenantUser.objects.filter(
                        tenant_id=tenant_id,
                        user_id=user_id
                    ).first()

                    if existing_relation:
                        # 恢复软删除的记录
                        if existing_relation.is_deleted:
                            existing_relation.is_deleted = False
                            existing_relation.deleted_at = None

                        # 更新字段
                        existing_relation.is_primary = user_data.get("is_primary", False)
                        existing_relation.is_assigned = True
                        existing_relation.expires_at = user_data.get("expires_at")
                        if "metadata" in user_data:
                            existing_relation.metadata = user_data["metadata"]

                        await existing_relation.save()
                        created_relations.append(existing_relation)
                    else:
                        # 创建新关联
                        new_relation = await TenantUser.create(
                            tenant_id=tenant_id,
                            user_id=user_id,
                            is_primary=user_data.get("is_primary", False),
                            is_assigned=True,
                            expires_at=user_data.get("expires_at"),
                            metadata=user_data.get("metadata", {})
                        )
                        created_relations.append(new_relation)

                    success_count += 1

                except Exception as e:
                    # 记录错误但继续处理其他用户
                    print(f"添加用户 {user_data.get('user_id')} 到租户失败: {e}")
                    # 可以根据需要决定是否回滚整个事务

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
            # 查询现有的关联（只处理未软删除的）
            tenant_users = await TenantUser.objects.filter(
                tenant_id=tenant_id,
                user_id__in=user_ids
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

    async def get_user_tenants(self, user_id: str) -> List[Dict[str, Any]]:
        """
        获取用户所属的所有租户（包括关联信息）
        :param user_id: 用户ID
        :return: 租户关联信息列表
        """
        # 查询用户的所有租户关联
        tenant_users = await TenantUser.objects.filter(
            user_id=user_id,
            is_assigned=True
        ).select_related('tenant').all()

        result = []
        for tu in tenant_users:
            result.append({
                "tenant_id": tu.tenant_id,
                "tenant_code": tu.tenant.code if tu.tenant else None,
                "tenant_name": tu.tenant.name if tu.tenant else None,
                "is_primary": tu.is_primary,
                "is_assigned": tu.is_assigned,
                "expires_at": tu.expires_at,
                "metadata": tu.metadata,
                "created_at": tu.created_at,
                "updated_at": tu.updated_at
            })

        return result

    async def set_primary_tenant(self, user_id: str, tenant_id: str) -> bool:
        """
        设置用户的主租户
        :param user_id: 用户ID
        :param tenant_id: 租户ID
        :return: 操作成功返回True，否则返回False
        """
        async with self.transaction():
            # 1. 检查关联是否存在
            tenant_user = await TenantUser.objects.filter(
                tenant_id=tenant_id,
                user_id=user_id
            ).first()

            if not tenant_user:
                return False

            # 2. 取消其他主租户
            await TenantUser.objects.filter(
                user_id=user_id,
                is_primary=True
            ).exclude(id=tenant_user.id).update(is_primary=False)

            # 3. 设置新的主租户
            tenant_user.is_primary = True
            await tenant_user.save()

            return True

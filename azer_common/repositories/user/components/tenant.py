# azer_common/repositories/user/components/tenant.py
from typing import List, Optional, Tuple
from tortoise.transactions import in_transaction
from azer_common.models.relations.tenant_user import TenantUser
from azer_common.models.tenant.model import Tenant
from azer_common.repositories.base_component import BaseComponent
from azer_common.utils.time import utc_now


class UserTenantComponent(BaseComponent):
    async def get_user_tenants(
            self,
            user_id: str,
            is_valid: bool = True,
            offset: int = 0,
            limit: int = 20
    ) -> Tuple[List[Tenant], int]:
        """
        获取用户所属的所有租户列表（支持分页）
        :param user_id: 用户ID
        :param is_valid: 是否仅返回有效关联（已分配+未过期+未软删除）
        :param offset: 分页偏移量
        :param limit: 分页大小
        :return: 租户列表、总数量
        """
        # 先获取用户-租户关联关系
        query = TenantUser.filter(user_id=user_id, is_deleted=False)
        if is_valid:
            query = query.filter(is_assigned=True).exclude(
                expires_at__lte=utc_now()
            )

        # 关联租户数据并分页
        query = query.select_related("tenant").order_by("-created_at")
        total = await query.count()
        tenant_users = await query.offset(offset).limit(limit).all()

        # 提取租户实例（过滤已禁用/已删除的租户）
        tenants = []
        for tu in tenant_users:
            tenant = tu.tenant
            if tenant and not tenant.is_deleted and tenant.is_enabled:
                tenants.append(tenant)

        return tenants, total

    async def get_primary_tenant(self, user_id: str) -> Optional[Tenant]:
        """
        获取用户的主租户（唯一）
        :param user_id: 用户ID
        :return: 主租户实例/None
        """
        tenant_user = await TenantUser.filter(
            user_id=user_id,
            is_primary=True,
            is_deleted=False,
            is_assigned=True
        ).exclude(expires_at__lte=utc_now()).select_related("tenant").first()

        if not tenant_user or not tenant_user.tenant:
            return None

        # 校验租户有效性
        tenant = tenant_user.tenant
        return tenant if (not tenant.is_deleted and tenant.is_enabled) else None

    async def set_primary_tenant(self, user_id: str, tenant_id: str) -> bool:
        """
        设置用户的主租户（自动取消原主租户）
        :param user_id: 用户ID
        :param tenant_id: 租户ID
        :return: 操作成功返回True
        """
        async with in_transaction():
            # 1. 校验用户和租户关联关系是否存在且有效
            tenant_user = await TenantUser.filter(
                user_id=user_id,
                tenant_id=tenant_id,
                is_deleted=False,
                is_assigned=True
            ).exclude(expires_at__lte=utc_now()).first()

            if not tenant_user:
                raise ValueError(f"用户{user_id}未关联到租户{tenant_id}或关联已失效")

            # 2. 取消原主租户
            await TenantUser.filter(
                user_id=user_id,
                is_primary=True,
                is_deleted=False
            ).update(is_primary=False)

            # 3. 设置新主租户
            tenant_user.is_primary = True
            await tenant_user.save(update_fields=["is_primary", "updated_at"])

            return True

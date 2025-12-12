# azer_common/repositories/tenant/components/base.py
from typing import List, Optional, Tuple
from azer_common.models.relations.tenant_user import TenantUser
from azer_common.models.tenant.model import Tenant
from azer_common.repositories.base_component import BaseComponent
from azer_common.utils.time import utc_now


class TenantBaseComponent(BaseComponent):
    """租户组件基础组件"""

    async def get_by_code(self, code: str) -> Optional[Tenant]:
        """
        根据租户编码获取租户信息
        :param code: 租户编码
        :return: 租户实例或None
        """
        return await self.get_by_field('code', code)

    async def check_code_exists(self, code: str, exclude_id: Optional[str] = None) -> bool:
        """
        检查租户编码是否已存在
        :param code: 租户编码
        :param exclude_id: 排除的租户ID（用于更新场景）
        :return: 存在返回True，否则返回False
        """
        query = await self.get_by_field('code', code)
        if exclude_id:
            query = query.exclude(id=exclude_id)
        return await query.exists()

    async def check_user_exists(self, user_id: str, tenant_id: str, check_valid: bool = True) -> bool:
        """
        检查用户是否属于指定租户（且关联有效）
        :param user_id: 用户ID
        :param tenant_id: 租户ID
        :param check_valid: 是否检查有效性（已分配+未过期）
        :return: 存在有效关联返回True
        """

        query = TenantUser.objects.filter(
            user_id=user_id,
            tenant_id=tenant_id
        )

        if check_valid:
            query = query.filter(
                is_assigned=True
            ).exclude(
                expires_at__lte=utc_now()
            )

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
        return await self.model.objects.filter(
            is_enabled=True,
            expired_at__isnull=False,
            expired_at__lte=now
        ).all()

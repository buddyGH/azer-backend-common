# azer_common/repositories/tenant/repository.py
from azer_common.repositories.base_repository import BaseRepository
from azer_common.models.tenant.model import Tenant
from .components import (
    TenantBaseComponent,
    TenantRoleComponent,
    TenantUserComponent
)


class TenantRepository(BaseRepository[Tenant]):
    """租户数据访问层，提供租户相关的数据库操作"""

    def __init__(self):
        super().__init__(Tenant)
        self.default_search_fields = ['code', 'name', 'contact', 'mobile']
        self.system_protected_fields = super().system_protected_fields + ['code', 'is_system']
        self._base = TenantBaseComponent(self)
        self._role = TenantRoleComponent(self)
        self._user = TenantUserComponent(self)

    # ========== 属性路由 ==========
    @property
    def base(self) -> TenantBaseComponent:
        """基础查询操作"""
        return self._base

    @property
    def user(self) -> TenantUserComponent:
        """用户管理操作"""
        return self._user

    @property
    def role(self) -> TenantRoleComponent:
        """角色管理操作"""
        return self._role

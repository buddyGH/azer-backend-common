# azer_common/repositories/role/repository.py
from azer_common.repositories.base_repository import BaseRepository
from azer_common.models.role.model import Role
from .components import RoleBaseComponent, RolePermissionComponent


class RoleRepository(BaseRepository[Role]):
    """角色数据访问层，提供角色相关的数据库操作"""

    def __init__(self):
        super().__init__(Role)
        self.default_search_fields = ["code", "name", "description", "role_type"]
        self.system_protected_fields = super().system_protected_fields + [
            "is_system",
            "tenant_id",
            "code",
            "parent_id",
        ]
        self._base = RoleBaseComponent(self)
        self._perm = RolePermissionComponent(self)

    # ========== 属性路由 ==========
    @property
    def base(self) -> RoleBaseComponent:
        """基础查询操作"""
        return self._base

    @property
    def perm(self) -> RolePermissionComponent:
        """用户管理操作"""
        return self._perm

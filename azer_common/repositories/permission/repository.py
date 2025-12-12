# azer_common/repositories/permission/repository.py
from azer_common.repositories.base_repository import BaseRepository
from azer_common.models.permission.model import Permission
from .components import (
    PermissionBaseComponent,
)


class PermissionRepository(BaseRepository[Permission]):
    """权限数据访问层，提供权限相关的数据库操作"""

    def __init__(self):
        super().__init__(Permission)
        self.default_search_fields = ["code", "name", "description", "category", "module"]
        self.system_protected_fields = super().system_protected_fields + [
            "is_system",
            "code",
            "tenant_id",
        ]
        self._base = PermissionBaseComponent(self)

    # ========== 属性路由 ==========
    @property
    def base(self) -> PermissionBaseComponent:
        """基础查询操作"""
        return self._base

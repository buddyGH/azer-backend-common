# azer_common/models/relations/__init__.py
from .tenant_user import TenantUser
from .user_role import UserRole
from .role_permission import RolePermission

__all__ = ["TenantUser", "UserRole", "RolePermission"]

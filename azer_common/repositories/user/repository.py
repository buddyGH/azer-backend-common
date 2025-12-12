# azer_common/repositories/user/repository.py
from azer_common.models.user.model import User
from azer_common.repositories.base_repository import BaseRepository
from .components import (
    UserBaseComponent,
    UserStatusComponent,
    UserTenantComponent,
    UserRoleComponent,
    UserStatsComponent,
)


class UserRepository(BaseRepository[User]):
    """用户数据访问层"""

    def __init__(self):
        super().__init__(User)
        self.default_search_fields = ["username", "nick_name", "real_name", "email", "mobile"]
        self._base = UserBaseComponent(self)
        self._status = UserStatusComponent(self)
        self._tenant = UserTenantComponent(self)
        self._role = UserRoleComponent(self)
        self._stats = UserStatsComponent(self)

    # ========== 属性路由 ==========
    @property
    def base(self) -> UserBaseComponent:
        """基础查询操作"""
        return self._base

    @property
    def status(self) -> UserStatusComponent:
        """状态管理操作"""
        return self._status

    @property
    def tenant(self) -> UserTenantComponent:
        """租户管理操作"""
        return self._tenant

    @property
    def role(self) -> UserRoleComponent:
        """角色管理操作"""
        return self._role

    @property
    def stats(self) -> UserStatsComponent:
        """统计分析操作"""
        return self._stats

# azer_common/repositories/auth/repository.py
from azer_common.models.auth.model import UserCredential
from azer_common.repositories.base_repository import BaseRepository
from .components import (
    AuthBaseComponent,
)


class UserCredentialRepository(BaseRepository[UserCredential]):
    """用户认证信息仓储层，处理数据库操作与业务逻辑解耦"""

    def __init__(self):
        super().__init__(UserCredential)
        self.default_search_fields = []
        self.system_protected_fields = super().system_protected_fields + [
            # 核心关联字段
            "user_id",  # 关联用户ID，创建后不应修改
            # 敏感认证字段
            "password",
            "mfa_secret",
            "backup_codes",
            "oauth_uid",
            # 自动更新的统计字段（应由系统逻辑更新）
            "failed_login_attempts",
            "login_count",
            "total_online_duration",
            "last_login_at",
            "last_login_ip",
            "password_changed_at",
            "password_expires_at",
            # 验证状态字段（应由验证流程自动更新）
            "email_verified_at",
            "mobile_verified_at",
            "mfa_verified_at",
            # 注册信息（创建后不应修改）
            "registration_ip",
            "registration_source",
        ]
        self._base = AuthBaseComponent(self)

    # ========== 属性路由 ==========
    @property
    def base(self) -> AuthBaseComponent:
        """基础查询操作"""
        return self._base

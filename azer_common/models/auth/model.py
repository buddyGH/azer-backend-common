# azer_common/models/auth/model.py
import argon2
from argon2 import PasswordHasher
from tortoise import fields
from azer_common.models.base import BaseModel
from azer_common.models.enums.base import MFATypeEnum
from azer_common.utils.time import add_days, utc_now
from azer_common.utils.validators import validate_password
from typing import Optional


# 复用密码哈希单例
PH_SINGLETON = PasswordHasher()


class UserCredential(BaseModel):
    """用户认证表 - 存储认证相关信息"""

    # 关联用户
    user = fields.OneToOneField("models.User", related_name="auth", on_delete=fields.CASCADE, description="关联用户")

    # 认证凭证
    password = fields.CharField(
        max_length=200,
        description="密码（argon2 哈希存储）",
        null=True,  # 允许为空，支持第三方登录用户
        write_only=True,
    )

    # 认证状态
    failed_login_attempts = fields.IntField(default=0, description="连续登录失败次数")
    password_changed_at = fields.DatetimeField(null=True, description="密码最后修改时间")

    # MFA认证
    mfa_enabled = fields.BooleanField(default=False, description="是否启用MFA")
    mfa_secret = fields.CharField(max_length=100, null=True, write_only=True, description="MFA密钥")
    backup_codes = fields.JSONField(null=True, write_only=True, description="备份验证码")
    mfa_type = fields.CharEnumField(MFATypeEnum, default=MFATypeEnum.NONE, description="MFA认证类型")
    mfa_verified_at = fields.DatetimeField(null=True, description="MFA最后验证时间")

    # 第三方登录（保留基本信息，token存Redis）
    oauth_platform = fields.CharField(max_length=20, null=True, description="第三方登录平台")
    oauth_uid = fields.CharField(max_length=100, null=True, index=True, description="第三方平台唯一ID")

    # 验证状态
    email_verified_at = fields.DatetimeField(null=True, description="邮箱验证时间")
    mobile_verified_at = fields.DatetimeField(null=True, description="手机验证时间")

    # 登录统计
    login_count = fields.IntField(default=0, description="登录次数")
    total_online_duration = fields.IntField(default=0, description="总在线时长（秒）")
    last_login_at = fields.DatetimeField(null=True, description="最后登录时间")
    last_login_ip = fields.CharField(max_length=45, null=True, description="最后登录IP")
    registration_ip = fields.CharField(max_length=45, null=True, description="注册IP")
    registration_source = fields.CharField(max_length=50, null=True, description="注册来源")

    # 安全相关
    password_expires_at = fields.DatetimeField(null=True, description="密码过期时间")

    class Meta:
        table = "azer_user_credential"
        table_description = "用户认证表"
        indexes = [
            ("oauth_platform", "oauth_uid"),  # 复合索引
        ]
        unique_together = [("oauth_platform", "oauth_uid")]

    class PydanticMeta:
        include = {
            # 核心标识
            "id",
            "user_id",
            # 认证状态（非敏感）
            "failed_login_attempts",
            "password_changed_at",
            "password_expires_at",
            # MFA 状态（不含密钥）
            "mfa_enabled",
            "mfa_type",
            "mfa_verified_at",
            # 验证状态
            "email_verified_at",
            "mobile_verified_at",
            # 登录统计（非敏感）
            "login_count",
            "last_login_at",
            "last_login_ip",
        }

    @property
    def is_verified(self) -> bool:
        """检查是否已验证（邮箱或手机）"""
        return bool(self.email_verified_at or self.mobile_verified_at)

    @property
    def is_email_verified(self) -> bool:
        """检查邮箱是否已验证"""
        return bool(self.email_verified_at)

    @property
    def is_mobile_verified(self) -> bool:
        """检查手机是否已验证"""
        return bool(self.mobile_verified_at)

    @property
    def requires_mfa(self) -> bool:
        """检查是否需要MFA验证"""
        return self.mfa_enabled and self.mfa_type != MFATypeEnum.NONE

    @property
    def has_password(self) -> bool:
        """检查是否设置了密码"""
        return bool(self.password)

    @property
    def days_since_password_change(self) -> Optional[int]:
        """获取密码修改天数（如果未设置返回None）"""
        if not self.password_changed_at:
            return None
        delta = utc_now() - self.password_changed_at
        return delta.days

    @property
    def days_since_last_login(self) -> Optional[int]:
        """获取上次登录天数（如果未登录返回None）"""
        if not self.last_login_at:
            return None
        delta = utc_now() - self.last_login_at
        return delta.days

    # 密码相关方法
    def set_password(self, password: str, password_expire_days: Optional[int] = None):
        """设置密码

        Args:
            password: 明文密码
            password_expire_days: 密码过期天数，None表示不过期
        """
        validate_password(password)
        self.password = PH_SINGLETON.hash(password)
        self.password_changed_at = utc_now()
        self.failed_login_attempts = 0  # 重置失败计数

        # 设置密码过期时间
        if password_expire_days is not None:
            self.password_expires_at = add_days(days=password_expire_days)
        else:
            self.password_expires_at = None

    def check_password_match(self, password: str) -> bool:
        """检查密码是否匹配（不更新失败次数）"""
        if not self.password:
            return False

        try:
            return PH_SINGLETON.verify(self.password, password)
        except (argon2.exceptions.VerifyMismatchError, argon2.exceptions.VerificationError):
            return False

    def is_password_expired(self) -> bool:
        """检查密码是否过期"""
        if not self.password_expires_at:
            return False
        return utc_now() > self.password_expires_at

    def get_mfa_info(self) -> dict:
        """获取MFA相关信息"""
        return {
            "mfa_enabled": self.mfa_enabled,
            "mfa_type": self.mfa_type.value if self.mfa_type else None,
            "mfa_verified_at": self.mfa_verified_at,
            "requires_mfa": self.requires_mfa,
        }

    def get_verification_status(self) -> dict:
        """获取验证状态信息"""
        return {
            "email_verified": self.is_email_verified,
            "mobile_verified": self.is_mobile_verified,
            "fully_verified": self.is_verified,
            "email_verified_at": self.email_verified_at,
            "mobile_verified_at": self.mobile_verified_at,
        }

    # 便捷方法
    def get_security_info(self) -> dict:
        """获取安全信息摘要（用于日志或审计）"""
        return {
            "user_id": self.user_id,
            "mfa_enabled": self.mfa_enabled,
            "mfa_type": self.mfa_type.value if self.mfa_type else None,
            "last_login_at": self.last_login_at,
            "password_changed_at": self.password_changed_at,
            "email_verified": self.is_email_verified,
            "mobile_verified": self.is_mobile_verified,
            "failed_login_attempts": self.failed_login_attempts,
            "password_expired": self.is_password_expired(),
        }


import azer_common.models.auth.signals

# azer_common/models/auth/model.py
import argon2
from argon2 import PasswordHasher
from tortoise import fields
from tortoise.transactions import in_transaction
from azer_common.models.base import BaseModel
from azer_common.models.enums.base import MFATypeEnum
from azer_common.utils.time import utc_now
from azer_common.utils.validators import validate_password
from datetime import timedelta
from typing import Optional

PH_SINGLETON = PasswordHasher()


class UserCredential(BaseModel):
    """用户认证表 - 存储认证相关信息"""

    # 关联用户
    user = fields.OneToOneField(
        'models.User',
        related_name='auth',
        on_delete=fields.CASCADE,
        description='关联用户'
    )

    # 认证凭证
    password = fields.CharField(
        max_length=200,
        description='密码（argon2 哈希存储）',
        null=True,  # 允许为空，支持第三方登录用户
        write_only=True
    )

    # 认证状态
    failed_login_attempts = fields.IntField(
        default=0,
        description='连续登录失败次数'
    )
    password_changed_at = fields.DatetimeField(
        null=True,
        description='密码最后修改时间'
    )

    # MFA认证
    mfa_enabled = fields.BooleanField(
        default=False,
        description='是否启用MFA'
    )
    mfa_secret = fields.CharField(
        max_length=100,
        null=True,
        write_only=True,
        description='MFA密钥'
    )
    backup_codes = fields.JSONField(
        null=True,
        write_only=True,
        description='备份验证码'
    )
    mfa_type = fields.CharEnumField(
        MFATypeEnum,
        default=MFATypeEnum.NONE,
        description='MFA认证类型'
    )
    mfa_verified_at = fields.DatetimeField(
        null=True,
        description='MFA最后验证时间'
    )

    # 第三方登录（保留基本信息，token存Redis）
    oauth_platform = fields.CharField(
        max_length=20,
        null=True,
        description='第三方登录平台'
    )
    oauth_uid = fields.CharField(
        max_length=100,
        null=True,
        index=True,
        description='第三方平台唯一ID'
    )

    # 验证状态
    email_verified_at = fields.DatetimeField(
        null=True,
        description='邮箱验证时间'
    )
    mobile_verified_at = fields.DatetimeField(
        null=True,
        description='手机验证时间'
    )

    # 登录统计
    login_count = fields.IntField(
        default=0,
        description='登录次数'
    )
    total_online_duration = fields.IntField(
        default=0,
        description='总在线时长（秒）'
    )
    last_login_at = fields.DatetimeField(
        null=True,
        description='最后登录时间'
    )
    last_login_ip = fields.CharField(
        max_length=45,
        null=True,
        description='最后登录IP'
    )
    registration_ip = fields.CharField(
        max_length=45,
        null=True,
        description='注册IP'
    )
    registration_source = fields.CharField(
        max_length=50,
        null=True,
        description='注册来源'
    )

    # 安全相关
    password_expires_at = fields.DatetimeField(
        null=True,
        description='密码过期时间'
    )

    class Meta:
        table = "azer_user_credential"
        table_description = '用户认证表'
        indexes = [
            ("oauth_platform", "oauth_uid"),  # 复合索引
        ]
        unique_together = [("oauth_platform", "oauth_uid")]

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
            self.password_expires_at = utc_now() + timedelta(days=password_expire_days)
        else:
            self.password_expires_at = None

    async def verify_password(self, password: str) -> bool:
        """验证密码（带并发安全保护）"""
        if not self.password:
            return False

        async with in_transaction():
            # 重新加载最新数据并加锁，避免脏读
            fresh_instance = await UserCredential.objects.filter(id=self.id).select_for_update().first()
            if not fresh_instance:
                return False

            try:
                is_valid = PH_SINGLETON.verify(fresh_instance.password, password)
            except (argon2.exceptions.VerifyMismatchError,
                    argon2.exceptions.VerificationError):
                is_valid = False

            if is_valid:
                fresh_instance.failed_login_attempts = 0
                fresh_instance.last_login_at = utc_now()
            else:
                fresh_instance.failed_login_attempts += 1

            await fresh_instance.save()

            # 更新当前实例状态
            await self.refresh_from_db()

            return is_valid

    def check_password_match(self, password: str) -> bool:
        """检查密码是否匹配（不更新失败次数）"""
        if not self.password:
            return False

        try:
            return PH_SINGLETON.verify(self.password, password)
        except (argon2.exceptions.VerifyMismatchError,
                argon2.exceptions.VerificationError):
            return False

    async def change_password(
            self, old_password: str, new_password: str,
            password_expire_days: Optional[int] = None) -> bool:
        """安全地更改密码

        Args:
            old_password: 旧密码
            new_password: 新密码
            password_expire_days: 新密码过期天数,若为空则永不过期

        Returns:
            bool: 是否成功修改
        """
        async with in_transaction():
            # 加行锁，确保拿到最新数据
            fresh_self = await UserCredential.objects.filter(id=self.id).select_for_update().first()
            if not fresh_self:
                return False

            if not fresh_self.check_password_match(old_password):
                return False
            if fresh_self.check_password_match(new_password):
                return False
            try:
                validate_password(new_password)
            except ValueError:
                return False
            fresh_self.set_password(new_password, password_expire_days)
            await fresh_self.save()
            await self.refresh_from_db()
            return True

    def is_password_expired(self) -> bool:
        """检查密码是否过期"""
        if not self.password_expires_at:
            return False
        return utc_now() > self.password_expires_at

    # MFA方法
    async def enable_mfa(self, mfa_type: MFATypeEnum, secret: str, backup_codes: list):
        """启用MFA"""
        self.mfa_enabled = True
        self.mfa_type = mfa_type
        self.mfa_secret = secret
        self.backup_codes = backup_codes
        self.mfa_verified_at = utc_now()
        await self.save()

    async def disable_mfa(self):
        """禁用MFA"""
        self.mfa_enabled = False
        self.mfa_type = MFATypeEnum.NONE
        self.mfa_secret = None
        self.backup_codes = None
        self.mfa_verified_at = None
        await self.save()

    # 验证方法
    async def set_email_verified(self, verified: bool = True):
        """设置邮箱验证状态

        Args:
            verified: 是否已验证
        """
        if verified:
            self.email_verified_at = utc_now()
        else:
            self.email_verified_at = None
        await self.save(update_fields=['email_verified_at'])

    async def set_mobile_verified(self, verified: bool = True):
        """设置手机验证状态

        Args:
            verified: 是否已验证
        """
        if verified:
            self.mobile_verified_at = utc_now()
        else:
            self.mobile_verified_at = None
        await self.save(update_fields=['mobile_verified_at'])

    # 登录记录
    async def record_login(self, ip_address: Optional[str] = None):
        """记录登录信息"""
        self.login_count += 1
        self.last_login_at = utc_now()
        self.last_login_ip = ip_address
        await self.save(update_fields=['login_count', 'last_login_at', 'last_login_ip'])

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

    @classmethod
    async def get_with_user(cls, user_id: int) -> Optional['UserCredential']:
        """一次性获取用户及其认证信息（减少查询次数）"""
        return await cls.objects.filter(user_id=user_id).select_related('user').first()

    # 便捷方法
    def get_security_info(self) -> dict:
        """获取安全信息摘要（用于日志或审计）"""
        return {
            'user_id': self.user_id,
            'mfa_enabled': self.mfa_enabled,
            'mfa_type': self.mfa_type.value if self.mfa_type else None,
            'last_login_at': self.last_login_at,
            'password_changed_at': self.password_changed_at,
            'email_verified': self.is_email_verified,
            'mobile_verified': self.is_mobile_verified,
            'failed_login_attempts': self.failed_login_attempts,
            'password_expired': self.is_password_expired(),
        }


import azer_common.models.auth.signals

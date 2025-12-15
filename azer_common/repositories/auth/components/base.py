# azer_common/repositories/auth/components/base.py
from azer_common.repositories.base_component import BaseComponent
from typing import Optional, List, Dict, Any
import argon2
from tortoise.transactions import in_transaction
from azer_common.models.auth.model import PH_SINGLETON, UserCredential
from azer_common.models.types.enums import MFATypeEnum
from azer_common.utils.time import utc_now
from azer_common.utils.validators import validate_password


class AuthBaseComponent(BaseComponent):

    async def get_by_user_id(self, user_id: int) -> Optional[UserCredential]:
        """根据用户ID获取认证信息（自动过滤软删除）"""
        return await self.query.filter(user_id=user_id).first()

    async def get_with_user(self, user_id: int) -> Optional[UserCredential]:
        """获取用户认证信息并关联用户数据（减少查询次数）"""
        return await self.query.filter(user_id=user_id).select_related("user").first()

    async def get_by_oauth_info(self, platform: str, oauth_uid: str) -> Optional[UserCredential]:
        """根据第三方登录信息获取认证记录"""
        return await self.query.filter(oauth_platform=platform, oauth_uid=oauth_uid).first()

    async def verify_password(self, user_id: int, password: str) -> bool:
        """验证密码（带并发安全保护，更新失败次数）"""
        async with in_transaction():
            # 加行锁获取最新数据，避免脏读
            credential = await self.query.filter(user_id=user_id).select_for_update().first()
            if not credential or not credential.password:
                return False

            try:
                is_valid = PH_SINGLETON.verify(credential.password, password)
            except (argon2.exceptions.VerifyMismatchError, argon2.exceptions.VerificationError):
                is_valid = False

            # 更新失败次数/登录时间
            if is_valid:
                credential.failed_login_attempts = 0
                credential.last_login_at = utc_now()
            else:
                credential.failed_login_attempts += 1

            await credential.save()
            return is_valid

    async def change_password(
        self, user_id: int, old_password: str, new_password: str, password_expire_days: Optional[int] = None
    ) -> bool:
        """安全修改密码（验证旧密码+事务保护）"""
        async with in_transaction():
            credential = await self.query.filter(user_id=user_id).select_for_update().first()
            if not credential:
                return False

            # 验证旧密码
            if not credential.check_password_match(old_password):
                return False

            # 检查新旧密码是否相同
            if credential.check_password_match(new_password):
                return False

            # 验证新密码格式并设置
            try:
                validate_password(new_password)
            except ValueError:
                return False

            credential.set_password(new_password, password_expire_days)
            await credential.save()
            return True

    async def set_password(self, user_id: int, password: str, password_expire_days: Optional[int] = None) -> bool:
        """直接设置密码（无需验证旧密码，用于重置场景）"""
        credential = await self.get_by_user_id(user_id)
        if not credential:
            return False

        try:
            validate_password(password)
        except ValueError:
            return False

        credential.set_password(password, password_expire_days)
        await credential.save()
        return True

    async def enable_mfa(self, user_id: int, mfa_type: MFATypeEnum, secret: str, backup_codes: list) -> bool:
        """启用MFA认证"""
        credential = await self.get_by_user_id(user_id)
        if not credential:
            return False

        credential.mfa_enabled = True
        credential.mfa_type = mfa_type
        credential.mfa_secret = secret
        credential.backup_codes = backup_codes
        credential.mfa_verified_at = utc_now()
        await credential.save()
        return True

    async def disable_mfa(self, user_id: int) -> bool:
        """禁用MFA认证"""
        credential = await self.get_by_user_id(user_id)
        if not credential:
            return False

        credential.mfa_enabled = False
        credential.mfa_type = MFATypeEnum.NONE
        credential.mfa_secret = None
        credential.backup_codes = None
        credential.mfa_verified_at = None
        await credential.save()
        return True

    async def set_email_verified(self, user_id: int, verified: bool = True) -> bool:
        """设置邮箱验证状态"""
        credential = await self.get_by_user_id(user_id)
        if not credential:
            return False

        credential.email_verified_at = utc_now() if verified else None
        await credential.save(update_fields=["email_verified_at"])
        return True

    async def set_mobile_verified(self, user_id: int, verified: bool = True) -> bool:
        """设置手机验证状态"""
        credential = await self.get_by_user_id(user_id)
        if not credential:
            return False

        credential.mobile_verified_at = utc_now() if verified else None
        await credential.save(update_fields=["mobile_verified_at"])
        return True

    async def record_login(self, user_id: int, ip_address: Optional[str] = None) -> bool:
        """记录用户登录信息（次数、时间、IP）"""
        credential = await self.get_by_user_id(user_id)
        if not credential:
            return False

        credential.login_count += 1
        credential.last_login_at = utc_now()
        credential.last_login_ip = ip_address
        await credential.save(update_fields=["login_count", "last_login_at", "last_login_ip"])
        return True

    async def reset_failed_attempts(self, user_id: int) -> bool:
        """重置登录失败次数"""
        credential = await self.get_by_user_id(user_id)
        if not credential:
            return False

        credential.failed_login_attempts = 0
        await credential.save(update_fields=["failed_login_attempts"])
        return True

    async def update_login_duration(self, user_id: int, duration_seconds: int) -> bool:
        """更新用户在线时长"""
        credential = await self.get_by_user_id(user_id)
        if not credential:
            return False

        credential.total_online_duration += duration_seconds
        await credential.save(update_fields=["total_online_duration"])
        return True

    async def get_security_summary(self, user_id: int) -> Optional[Dict[str, Any]]:
        """获取用户安全信息摘要（用于审计/日志）"""
        credential = await self.get_by_user_id(user_id)
        if not credential:
            return None
        return credential.get_security_info()

    async def batch_get_security_summary(self, user_ids: List[int]) -> Dict[int, Dict[str, Any]]:
        """批量获取用户安全信息摘要"""
        credentials = await self.get_by_ids(user_ids)
        return {cred.user_id: cred.get_security_info() for cred in credentials}

    async def check_password_expired(self, user_id: int) -> bool:
        """检查用户密码是否过期"""
        credential = await self.get_by_user_id(user_id)
        if not credential:
            return False
        return credential.is_password_expired()

    async def create_with_user(
        self,
        user_id: int,
        password: Optional[str] = None,
        registration_ip: Optional[str] = None,
        registration_source: Optional[str] = None,
        **kwargs,
    ) -> UserCredential:
        """创建用户认证信息（关联用户ID）"""
        data = {
            "user_id": user_id,
            "registration_ip": registration_ip,
            "registration_source": registration_source,
            **kwargs,
        }

        # 若传入密码则自动哈希
        if password:
            validate_password(password)
            data["password"] = PH_SINGLETON.hash(password)
            data["password_changed_at"] = utc_now()

        return await self.create(**data)

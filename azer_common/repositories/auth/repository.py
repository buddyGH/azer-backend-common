# azer_common/repositories/auth/repository.py
# azer_common/repositories/auth/user_credential_repository.py
from typing import Optional, List, Dict, Any, Tuple
from tortoise.expressions import Q
from tortoise.transactions import in_transaction
from argon2.exceptions import VerifyMismatchError, VerificationError

from azer_common.models.auth.model import UserCredential, MFATypeEnum
from azer_common.repositories.base import BaseRepository
from azer_common.utils.time import utc_now
from azer_common.utils.validators import validate_password
from azer_common.models.auth.model import PH_SINGLETON


class UserCredentialRepository(BaseRepository[UserCredential]):
    """用户认证数据仓库"""

    def __init__(self):
        super().__init__(UserCredential)

    async def get_by_user_id(self, user_id: int) -> Optional[UserCredential]:
        """根据用户ID获取认证信息"""
        return await self.get_query().filter(user_id=user_id).first()

    async def get_by_oauth(self, platform: str, uid: str) -> Optional[UserCredential]:
        """根据第三方平台信息获取认证信息"""
        return await self.get_query().filter(
            oauth_platform=platform,
            oauth_uid=uid
        ).first()

    async def verify_password(
            self,
            credential_id: int,
            password: str
    ) -> Tuple[bool, Optional[UserCredential]]:
        """验证密码（带事务和行锁保护）

        Returns:
            Tuple[bool, Optional[UserCredential]]: (是否验证成功, 更新后的实例)
        """
        async with in_transaction():
            # 获取并锁定记录
            fresh_instance = await UserCredential.objects.select_for_update().get_or_none(id=credential_id)
            if not fresh_instance or not fresh_instance.password:
                return False, None

            try:
                is_valid = PH_SINGLETON.verify(fresh_instance.password, password)
            except (VerifyMismatchError, VerificationError):
                is_valid = False

            if is_valid:
                fresh_instance.failed_login_attempts = 0
                fresh_instance.last_login_at = utc_now()
            else:
                fresh_instance.failed_login_attempts += 1

            await fresh_instance.save()
            return is_valid, fresh_instance

    async def change_password(
            self,
            credential_id: int,
            old_password: str,
            new_password: str,
            password_expire_days: Optional[int] = None
    ) -> bool:
        """安全地更改密码"""
        async with in_transaction():
            # 获取并锁定记录
            fresh_instance = await UserCredential.objects.select_for_update().get_or_none(id=credential_id)
            if not fresh_instance:
                return False

            # 验证旧密码
            try:
                if not fresh_instance.password or not PH_SINGLETON.verify(fresh_instance.password, old_password):
                    return False
            except (VerifyMismatchError, VerificationError):
                return False

            # 新密码不能与旧密码相同
            try:
                if PH_SINGLETON.verify(fresh_instance.password, new_password):
                    return False
            except (VerifyMismatchError, VerificationError):
                # 密码不匹配是正常的，继续执行
                pass

            # 验证新密码复杂度
            try:
                validate_password(new_password)
            except ValueError:
                return False

            # 设置新密码
            fresh_instance.password = PH_SINGLETON.hash(new_password)
            fresh_instance.password_changed_at = utc_now()
            fresh_instance.failed_login_attempts = 0

            # 设置密码过期时间
            if password_expire_days is not None:
                from azer_common.utils.time import add_days
                fresh_instance.password_expires_at = add_days(days=password_expire_days)
            else:
                fresh_instance.password_expires_at = None

            await fresh_instance.save()
            return True

    async def enable_mfa(
            self,
            credential_id: int,
            mfa_type: MFATypeEnum,
            secret: str,
            backup_codes: List[str]
    ) -> bool:
        """启用MFA"""
        update_data = {
            "mfa_enabled": True,
            "mfa_type": mfa_type,
            "mfa_secret": secret,
            "backup_codes": backup_codes,
            "mfa_verified_at": utc_now()
        }
        return await self.update(credential_id, **update_data) is not None

    async def disable_mfa(self, credential_id: int) -> bool:
        """禁用MFA"""
        update_data = {
            "mfa_enabled": False,
            "mfa_type": MFATypeEnum.NONE,
            "mfa_secret": None,
            "backup_codes": None,
            "mfa_verified_at": None
        }
        return await self.update(credential_id, **update_data) is not None

    async def update_email_verified(self, credential_id: int, verified: bool = True) -> bool:
        """更新邮箱验证状态"""
        update_data = {
            "email_verified_at": utc_now() if verified else None
        }
        return await self.update(credential_id, **update_data) is not None

    async def update_mobile_verified(self, credential_id: int, verified: bool = True) -> bool:
        """更新手机验证状态"""
        update_data = {
            "mobile_verified_at": utc_now() if verified else None
        }
        return await self.update(credential_id, **update_data) is not None

    async def record_login(
            self,
            credential_id: int,
            ip_address: Optional[str] = None
    ) -> bool:
        """记录登录信息"""
        # 先获取当前登录次数
        instance = await self.get_by_id(credential_id)
        if not instance:
            return False

        update_data = {
            "login_count": instance.login_count + 1,
            "last_login_at": utc_now(),
            "last_login_ip": ip_address
        }
        return await self.update(credential_id, **update_data) is not None

    async def reset_failed_attempts(self, credential_id: int) -> bool:
        """重置登录失败次数"""
        return await self.update(credential_id, failed_login_attempts=0) is not None

    async def search_by_login_history(
            self,
            last_login_days: Optional[int] = None,
            min_login_count: Optional[int] = None,
            offset: int = 0,
            limit: int = 20
    ) -> Tuple[List[UserCredential], int]:
        """根据登录历史搜索用户"""
        query = self.get_query()

        if last_login_days:
            from azer_common.utils.time import add_days
            cutoff_date = add_days(days=-last_login_days)
            query = query.filter(last_login_at__gte=cutoff_date)

        if min_login_count:
            query = query.filter(login_count__gte=min_login_count)

        total = await query.count()
        results = await query.offset(offset).limit(limit).all()
        return list(results), total

    async def get_security_stats(self, user_ids: List[int]) -> Dict[int, Dict[str, Any]]:
        """批量获取用户安全统计信息"""
        credentials = await self.get_query().filter(user_id__in=user_ids).all()

        stats = {}
        for cred in credentials:
            stats[cred.user_id] = {
                'mfa_enabled': cred.mfa_enabled,
                'mfa_type': cred.mfa_type.value if cred.mfa_type else None,
                'last_login_at': cred.last_login_at,
                'failed_attempts': cred.failed_login_attempts,
                'is_verified': bool(cred.email_verified_at or cred.mobile_verified_at),
                'password_expired': cred.is_password_expired(),
            }

        return stats
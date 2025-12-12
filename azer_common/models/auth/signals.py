# azer_common/models/auth/signals.py
from tortoise.signals import pre_save
from azer_common.models.auth.model import PH_SINGLETON, UserCredential
from azer_common.utils.is_password_hashed import is_password_hashed
from azer_common.utils.time import utc_now


@pre_save(UserCredential)
async def hash_user_credential_password(_sender, instance: UserCredential, _using_db, update_fields):
    """UserCredential的密码哈希处理器"""
    # 如果密码字段存在且不是哈希格式，进行哈希处理
    if instance.password and not is_password_hashed(instance.password):
        # 直接哈希，不设置过期时间（业务层通过set_password方法设置）
        instance.password = PH_SINGLETON.hash(instance.password)
        instance.password_changed_at = utc_now()
        instance.failed_login_attempts = 0

        if update_fields is not None:
            fields_to_add = ["password", "password_changed_at", "failed_login_attempts"]
            for field in fields_to_add:
                if field not in update_fields:
                    update_fields.append(field)

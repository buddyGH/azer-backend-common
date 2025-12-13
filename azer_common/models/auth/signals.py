# azer_common/models/auth/signals.py
from tortoise.signals import pre_save
from azer_common.models.auth.model import PH_SINGLETON, UserCredential
from azer_common.utils.is_password_hashed import is_password_hashed
from azer_common.utils.time import utc_now


@pre_save(UserCredential)
async def hash_user_credential_password(_sender, instance: UserCredential, _using_db, update_fields):
    """UserCredential的密码哈希处理器"""
    # 1. 跳过新建实例（新建时无旧值，且业务层应通过set_password设置密码）
    if not instance.pk:
        return

    # 2. 无密码或密码字段未变更 → 直接跳过
    if not instance.password or (update_fields and "password" not in update_fields):
        return

    # 3. 获取数据库中的旧密码（对比是否真的变更）
    old_instance = await UserCredential.get_or_none(id=instance.pk)
    if not old_instance or old_instance.password == instance.password:
        return  # 密码未变更，跳过所有操作

    # 4. 密码已变更：处理明文→哈希，更新附属字段
    password_updated = False
    if not is_password_hashed(instance.password):
        # 明文密码 → 自动哈希
        instance.password = PH_SINGLETON.hash(instance.password)
        password_updated = True

    # 5. 无论明文/哈希，只要密码变更就更新附属字段
    instance.password_changed_at = utc_now()
    instance.failed_login_attempts = 0
    instance.failed_login_at = None

    # 6. 更新update_fields（确保字段被保存）
    if update_fields is not None:
        fields_to_add = ["password_changed_at", "failed_login_attempts"]
        if password_updated:
            fields_to_add.append("password")  # 只有哈希转换时才加password
        for field in fields_to_add:
            if field not in update_fields:
                update_fields.append(field)

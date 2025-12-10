# azer_common/models/user/signals.py
from tortoise.signals import post_save, pre_save
from azer_common.models.user.model import User
from azer_common.models.auth.model import UserCredential


@post_save(User)
async def create_user_auth(_sender, instance: User, created: bool, _using_db, _update_fields):
    """创建用户时自动创建对应的 UserCredential 记录"""
    if created:
        await UserCredential.create(user=instance)


@pre_save(User)
async def sync_user_email_mobile(_sender, instance: User, _using_db, update_fields):
    """当用户的email或mobile字段发生变更时，重置对应的验证状态"""
    # 核心修正：pre_save无created参数，通过pk是否存在判断是否是更新操作
    # pk存在 = 更新，pk不存在 = 创建
    is_create = instance.pk is None
    if is_create or not update_fields:  # 仅处理更新操作，跳过创建
        return

    auth = await UserCredential.get_or_none(user_id=instance.id)
    if not auth:
        return

    # 获取更新前的旧数据（all_objects避免软删除过滤）
    old_instance = await User.all_objects.filter(id=instance.id).first()
    if not old_instance:
        return

    # 邮箱变更：重置验证状态
    if 'email' in update_fields and instance.email != old_instance.email:
        if auth.email_verified_at:
            auth.email_verified_at = None
            await auth.save(update_fields=['email_verified_at'])

    # 手机号变更：重置验证状态
    if 'mobile' in update_fields and instance.mobile != old_instance.mobile:
        if auth.mobile_verified_at:
            auth.mobile_verified_at = None
            await auth.save(update_fields=['mobile_verified_at'])
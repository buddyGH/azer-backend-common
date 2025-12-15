from tortoise.signals import pre_save
from azer_common.models.auth.model import PH_SINGLETON, UserCredential
from azer_common.utils.is_password_hashed import is_password_hashed
from azer_common.utils.time import utc_now
from azer_common.utils.validators import validate_password
from azer_common.models import PUBLIC_APP_LABEL


@pre_save(UserCredential)
async def hash_user_credential_password(_sender, instance: UserCredential, _using_db, update_fields):
    """UserCredential的密码哈希处理器"""
    """
        密码字段兜底防护：拦截所有写入数据库的操作
        处理场景：
        1. 直接赋值空字符串 → 抛异常
        2. 直接赋值明文 → 自动验证+哈希
        3. 直接赋值非法哈希 → 抛异常
        4. 合法哈希 → 放行
        5. 无密码（None）→ 放行（第三方登录场景）
        """
    # 场景1：无密码（None）→ 放行（第三方登录）
    if instance.password is None:
        return

    # 场景2：空字符串/全空白 → 抛异常
    if instance.password.strip() == "":
        raise ValueError("密码不能为空，禁止设置空字符串密码")

    # 场景3：字段未变更 → 放行
    if update_fields and "password" not in update_fields:
        return

    # 场景4：已是合法哈希 → 放行（包括set_password设置的哈希）
    if is_password_hashed(instance.password):
        # 兜底：确保附属字段有值（防止手动改哈希但没更改变更时间）
        if not instance.last_password_changed_at:
            instance.last_password_changed_at = utc_now()
            # 关键：把last_password_changed_at加入update_fields
            if update_fields is not None and "last_password_changed_at" not in update_fields:
                update_fields.append("last_password_changed_at")
        return

    # 场景5：明文密码（手动赋值）→ 自动验证+哈希（兜底）
    try:
        validate_password(instance.password)  # 验证明文格式
        # 加密并更新附属字段
        instance.password = PH_SINGLETON.hash(instance.password)
        instance.last_password_changed_at = utc_now()
        instance.failed_login_attempts = 0
        instance.failed_login_at = None

        # ========== 更新update_fields，确保新增字段被保存 ==========
        if update_fields is not None:
            # 需要保存的字段列表
            fields_to_add = ["last_password_changed_at", "failed_login_attempts", "failed_login_at"]
            for field in fields_to_add:
                if field not in update_fields:
                    update_fields.append(field)

    except ValueError as e:
        raise ValueError(f"明文密码格式错误：{str(e)}") from e


# TODO: 触发redis模块相关内容

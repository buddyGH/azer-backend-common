# azer_common/models/auth/password_history.py
# azer_common/models/auth/password_history.py
from tortoise import fields
from azer_common.models.base import BaseModel


class PasswordHistory(BaseModel):
    """用户密码历史表"""

    user = fields.ForeignKeyField("models.User", related_name="password_histories", description="关联用户")

    password_hash = fields.CharField(max_length=200, description="密码哈希值（存储格式与UserCredential.password相同）")

    # 可以添加额外字段用于分析
    changed_by = fields.ForeignKeyField("models.User", null=True, description="由谁修改的")

    change_reason = fields.CharField(
        max_length=100, null=True, description="修改原因（如：定期更换、疑似泄露、管理员重置等）"
    )

    class Meta:
        table = "azer_password_history"
        table_description = "用户密码历史表"
        indexes = [
            ("user_id", "created_at"),
        ]

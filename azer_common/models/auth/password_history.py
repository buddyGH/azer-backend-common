# azer_common/models/auth/password_history.py
from tortoise import fields
from azer_common.models.base import BaseModel
from azer_common.models import PUBLIC_APP_LABEL


class PasswordHistory(BaseModel):
    """
    用户密码历史表。
    记录 UserCredential（用户认证凭证）的密码变更历史，用于安全审计与合规性检查。
    """

    credential = fields.ForeignKeyField(
        model_name=PUBLIC_APP_LABEL + ".UserCredential",
        related_name="password_histories",
        on_delete=fields.RESTRICT,
        description="关联的核心认证凭证",
    )

    password_hash = fields.CharField(
        max_length=200, description="历史密码的Argon2哈希值，格式与 UserCredential.password 一致"
    )

    # 额外字段用于审计分析
    changed_by = fields.ForeignKeyField(
        model_name=PUBLIC_APP_LABEL + ".User",
        null=True,
        on_delete=fields.SET_NULL,
        description="执行此次密码修改操作的用户（例如，管理员重置用户密码时记录管理员）",
    )

    change_reason = fields.CharField(
        max_length=100,
        null=True,
        description="修改原因，例如：用户主动修改、定期强制更换、疑似泄露后重置、管理员操作等",
    )

    class Meta:
        table = "azer_password_history"
        table_description = "用户认证凭证的密码变更历史表"
        indexes = [
            ("credential_id", "created_at"),
            ("created_at",),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"PasswordHistory for Credential#{self.credential_id} at {self.created_at}"

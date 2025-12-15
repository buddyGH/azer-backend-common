# azer_common/models/auth/oauth_connection.py
from tortoise import fields
from azer_common.models.base import BaseModel
from azer_common.utils.time import utc_now
from azer_common.models import PUBLIC_APP_LABEL


class OAuthConnection(BaseModel):
    """用户第三方登录连接表"""

    credential = fields.ForeignKeyField(
        model_name=PUBLIC_APP_LABEL + ".UserCredential",
        related_name="oauth_connections",
        on_delete=fields.CASCADE,
        description="关联的核心认证凭证",
    )

    platform = fields.CharField(max_length=20, description="第三方平台（如：google、github、wechat等）")

    platform_uid = fields.CharField(max_length=100, index=True, description="第三方平台唯一ID")

    # 平台相关信息（非token数据）
    platform_data = fields.JSONField(null=True, description="平台返回的用户数据（如头像、昵称等）")

    # 连接状态
    connected_at = fields.DatetimeField(default=utc_now, description="连接时间")

    last_used_at = fields.DatetimeField(null=True, description="最后使用时间")

    is_active = fields.BooleanField(default=True, description="是否活跃连接")

    revoked_at = fields.DatetimeField(null=True, description="撤销连接时间")

    revoke_reason = fields.CharField(max_length=200, null=True, description="撤销原因")

    class Meta:
        table = "azer_oauth_connection"
        table_description = "用户第三方登录连接表"
        indexes = [
            ("platform", "platform_uid"),  # 快速通过平台ID查找用户
            ("is_active", "connected_at"),  # 清理不活跃连接
        ]
        unique_together = [("platform", "platform_uid")]

    def __str__(self) -> str:
        return f"{self.platform} ({self.platform_uid}) for Credential#{self.credential_id}"

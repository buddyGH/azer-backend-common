# azer_common/models/audit/role.py
from tortoise import fields

from azer_common.models.base import BaseModel
from azer_common.models.enums.base import UserRoleOperationType
from azer_common.utils.time import utc_now


class UserRoleAudit(BaseModel):
    """用户角色关联审计日志表"""
    user_role = fields.ForeignKeyField(
        'models.UserRole',
        related_name='audit_logs',
        description='关联的用户角色记录',
        on_delete=fields.CASCADE
    )
    operation_type = fields.CharEnumField(
        UserRoleOperationType,
        description='操作类型'
    )
    operated_by = fields.ForeignKeyField(
        'models.User',
        null=True,
        on_delete=fields.SET_NULL,
        related_name='operated_user_role_audits',
        description='操作人'
    )
    operated_at = fields.DatetimeField(
        default=utc_now,
        description='操作时间'
    )
    reason = fields.CharField(
        max_length=200,
        null=True,
        description='操作原因'
    )
    metadata = fields.JSONField(
        null=True,
        description='扩展元数据'
    )
    before_data = fields.JSONField(
        null=True,
        description='操作前的状态数据'
    )
    after_data = fields.JSONField(
        null=True,
        description='操作后的状态数据'
    )
    tenant_id = fields.CharField(
        max_length=64,
        null=True,
        description='租户ID（冗余）'
    )

    class Meta:
        table = "azer_user_role_audit"
        table_description = '用户角色关联审计日志表'
        indexes = [
            ("user_role_id", "operation_type", "operated_at"),
            ("operated_by", "operated_at"),
            ("tenant_id", "operated_at"),
        ]

    # 审计日志只读，禁止修改
    async def save(self, *args, **kwargs):
        if self.id:
            raise PermissionError("审计日志不允许修改")
        await super().save(*args, **kwargs)

    async def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'user_role_id': self.user_role_id,
            'operation_type': self.operation_type.value,
            'operated_by_id': self.operated_by_id,
            'operated_at': self.operated_at,
            'reason': self.reason,
            'metadata': self.metadata,
            'before_data': self.before_data,
            'after_data': self.after_data,
            'tenant_id': self.tenant_id,
        }

# azer_common/models/audit/role_permission.py
from typing import Any, Dict
from tortoise import fields
from azer_common.models.base import BaseModel
from azer_common.models.enums.base import RolePermissionOperationType
from azer_common.utils.time import utc_now


class RolePermissionAudit(BaseModel):
    """角色权限关联审计日志表（纯审计，与业务解耦）"""

    role_permission = fields.ForeignKeyField(
        "models.RolePermission", related_name="audit_logs", description="关联的权限关联记录", on_delete=fields.CASCADE
    )
    operation_type = fields.CharEnumField(RolePermissionOperationType, description="操作类型")
    operated_by = fields.ForeignKeyField(
        "models.User",
        null=True,
        on_delete=fields.SET_NULL,
        related_name="operated_role_permission_audits",
        description="操作人",
    )
    operated_at = fields.DatetimeField(default=utc_now, description="操作时间")
    reason = fields.CharField(max_length=200, null=True, description="操作原因")
    metadata = fields.JSONField(null=True, description="扩展元数据")
    before_data = fields.JSONField(null=True, description="操作前的状态数据")
    after_data = fields.JSONField(null=True, description="操作后的状态数据")
    tenant_id = fields.CharField(max_length=64, null=True, description="租户ID（冗余）")

    class Meta:
        table = "azer_role_permission_audit"
        table_description = "角色权限关联审计日志表"
        indexes = [
            ("role_permission_id", "operation_type", "operated_at"),
            ("operated_by", "operated_at"),
            ("tenant_id", "operated_at"),
        ]

    async def save(self, *args, **kwargs):
        if self.id:
            raise PermissionError("审计日志不允许修改")
        await super().save(*args, **kwargs)

    async def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "role_permission_id": self.role_permission_id,
            "operation_type": self.operation_type.value,
            "operated_by_id": self.operated_by_id,
            "operated_at": self.operated_at,
            "reason": self.reason,
            "metadata": self.metadata,
            "before_data": self.before_data,
            "after_data": self.after_data,
            "tenant_id": self.tenant_id,
        }


from azer_common.models.audit.signals import handle_role_permission_save

from tortoise import fields
from azer_common.models.audit.base import BaseAuditLog


class RolePermissionAudit(BaseAuditLog):
    """角色权限关联审计日志表（继承通用基类）"""

    role_permission = fields.ForeignKeyField(
        "models.RolePermission", related_name="audit_logs", on_delete=fields.CASCADE
    )

    class Meta:
        table = "azer_role_permission_audit"
        table_description = "角色权限关联审计日志表"


from azer_common.models.audit.signals import handle_role_permission_save

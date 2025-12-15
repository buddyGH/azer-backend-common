from tortoise import fields
from azer_common.models.audit.base import BaseAuditLog


class UserRoleAudit(BaseAuditLog):
    """用户角色关联审计日志表（继承通用基类）"""

    user_role = fields.ForeignKeyField("models.UserRole", related_name="audit_logs", on_delete=fields.CASCADE)

    class Meta:
        table = "azer_user_role_audit"
        table_description = "用户角色关联审计日志表"
        indexes = BaseAuditLog.Meta.indexes + []

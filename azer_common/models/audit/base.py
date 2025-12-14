# azer_common/models/audit/base.py
from typing import Any, Dict
from tortoise import fields
from azer_common.models.base import BaseModel
from azer_common.utils.time import utc_now


class BaseAuditLog(BaseModel):
    """审计日志通用基类（所有业务审计表继承）"""

    # 核心溯源字段
    business_id = fields.CharField(max_length=64, description="关联的业务记录ID（通用字段，替代xxx_id）")
    business_type = fields.CharField(max_length=32, description="业务类型（如role_permission/user_role/tenant）")
    operation_type = fields.CharField(max_length=32, description="操作类型（create/update/delete/soft_delete）")
    operated_by_id = fields.CharField(max_length=64, null=True, description="操作人ID（冗余，避免关联查询）")
    operated_by_name = fields.CharField(max_length=64, null=True, description="操作人名称（冗余）")
    operated_at = fields.DatetimeField(default=utc_now, description="操作时间")
    operated_ip = fields.CharField(max_length=64, null=True, description="操作IP地址")
    operated_terminal = fields.CharField(max_length=64, null=True, description="操作终端（web/app/api）")
    request_id = fields.CharField(max_length=64, null=True, description="请求ID（链路追踪）")

    # 业务字段
    reason = fields.CharField(max_length=200, null=True, description="操作原因")
    metadata = fields.JSONField(null=True, description="扩展元数据")
    before_data = fields.JSONField(null=True, description="操作前数据")
    after_data = fields.JSONField(null=True, description="操作后数据")

    # 多租户字段
    tenant_id = fields.CharField(max_length=64, null=True, description="租户ID")

    class Meta:
        abstract = True  # 抽象基类，不生成表
        indexes = [
            # 高频查询索引：租户+业务类型+操作时间（核心）
            ("tenant_id", "business_type", "operated_at"),
            # 辅助索引：操作人+操作时间
            ("operated_by_id", "operated_at"),
            # 辅助索引：业务ID+业务类型（快速关联业务记录）
            ("business_id", "business_type"),
        ]

    # 核心约束：审计日志不可修改/删除
    async def save(self, *args, **kwargs):
        if self.id:
            raise PermissionError("审计日志不允许修改")
        await super().save(*args, **kwargs)

    # 禁止物理删除
    async def delete(self, *args, **kwargs):
        raise PermissionError("审计日志不允许删除")

    async def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "business_id": self.business_id,
            "business_type": self.business_type,
            "operation_type": self.operation_type,
            "operated_by_id": self.operated_by_id,
            "operated_by_name": self.operated_by_name,
            "operated_at": self.operated_at,
            "operated_ip": self.operated_ip,
            "operated_terminal": self.operated_terminal,
            "request_id": self.request_id,
            "reason": self.reason,
            "metadata": self.metadata,
            "before_data": self.before_data,
            "after_data": self.after_data,
            "tenant_id": self.tenant_id,
        }

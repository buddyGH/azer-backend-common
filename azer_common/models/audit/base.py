# azer_common/models/audit/base.py
from typing import Any, Dict
from tortoise import fields
from azer_common.models.base import BaseModel
from azer_common.utils.time import utc_now


class BaseAuditLog(BaseModel):
    """审计日志通用基类"""

    # 核心溯源字段
    business_id = fields.CharField(max_length=64, description="关联的业务记录ID")
    business_type = fields.CharField(max_length=32, description="业务类型")
    operation_type = fields.CharField(max_length=32, description="操作类型")
    operated_by_id = fields.CharField(max_length=64, null=True, description="操作人ID")
    operated_by_name = fields.CharField(max_length=64, null=True, description="操作人名称")
    operated_at = fields.DatetimeField(default=utc_now, description="操作时间")
    operated_ip = fields.CharField(max_length=64, null=True, description="操作IP地址")
    operated_terminal = fields.CharField(max_length=64, null=True, description="操作终端")

    # 分布式追踪字段
    request_id = fields.CharField(max_length=64, null=True, description="请求ID（网关生成）")
    trace_id = fields.CharField(max_length=100, null=True, description="分布式追踪ID")

    # 微服务标识字段
    source_service = fields.CharField(max_length=50, null=True, description="操作来源服务")
    target_service = fields.CharField(max_length=50, null=True, description="操作目标服务")

    # 业务字段
    reason = fields.CharField(max_length=200, null=True, description="操作原因")
    metadata = fields.JSONField(null=True, description="扩展元数据")
    before_data = fields.JSONField(null=True, description="操作前数据")
    after_data = fields.JSONField(null=True, description="操作后数据")

    # 多租户字段
    tenant_id = fields.CharField(max_length=64, null=True, description="租户ID")

    class Meta:
        abstract = True
        indexes = [
            ("tenant_id", "business_type", "operation_type", "operated_at"),
            ("tenant_id", "business_type", "operated_at"),
            ("operated_by_id", "operated_at"),
            ("business_id", "business_type"),
            ("trace_id", "source_service"),  # 分布式追踪查询
            ("source_service", "target_service", "operated_at"),  # 服务间调用审计
        ]

    # 核心约束：审计日志不可修改/删除
    async def save(self, *args, **kwargs):
        if self._saved_in_db:
            raise PermissionError("审计日志不允许修改")
        await super().save(*args, **kwargs)

    # 禁止物理删除
    async def delete(self, *args, **kwargs):
        raise PermissionError("审计日志不允许删除")

    async def soft_delete(self, *args, **kwargs):
        raise PermissionError("审计日志不允许软删除")

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

from tortoise import fields
from azer_common.models import PUBLIC_APP_LABEL
from azer_common.models.audit.registry import register_audit
from azer_common.models.base import BaseModel
from azer_common.utils.time import utc_now


@register_audit(business_type="role_permission")
class RolePermission(BaseModel):
    """角色权限关联表，管理角色与权限的授予关系"""

    # 核心关联字段
    role = fields.ForeignKeyField(
        model_name=PUBLIC_APP_LABEL + ".Role",
        related_name="role_permissions",
        description="关联角色",
        on_delete=fields.RESTRICT,
        null=False,
    )
    permission = fields.ForeignKeyField(
        model_name=PUBLIC_APP_LABEL + ".Permission",
        related_name="permission_roles",
        description="关联权限",
        on_delete=fields.RESTRICT,
        null=False,
    )

    # 多租户字段
    tenant = fields.ForeignKeyField(
        model_name=PUBLIC_APP_LABEL + ".Tenant",
        related_name="role_permissions",
        description="所属租户（兼容全局权限）",
        on_delete=fields.RESTRICT,
        null=True,
        index=True,
    )

    # 状态控制字段
    is_granted = fields.BooleanField(default=True, description="是否授予该权限")
    effective_from = fields.DatetimeField(null=True, description="权限生效开始时间")
    effective_to = fields.DatetimeField(null=True, description="权限生效结束时间")
    metadata = fields.JSONField(null=True, description="扩展元数据")

    class Meta:
        table = "azer_role_permission"
        table_description = "角色权限关联表"
        unique_together = [
            ("role_id", "permission_id", "tenant_id", "is_deleted"),
        ]
        indexes = [
            ("tenant_id", "role_id", "is_granted", "is_deleted"),
            ("tenant_id", "permission_id", "is_granted", "is_deleted"),
            ("is_granted", "effective_to", "is_deleted"),
            ("permission_id", "is_granted", "tenant_id"),
        ]

    class PydanticMeta:
        include = {
            "role": {"id", "code", "name"},
            "permission": {"id", "code", "name"},
            "tenant": {"id", "code", "name"},
        }

    def __str__(self):
        """角色权限关联实例的字符串表示"""
        tenant_info = "[全局]" if self.tenant_id is None else f"[租户:{self.tenant_id}]"
        grant_status = "已授予" if self.is_granted else "未授予"
        return f"{tenant_info} 角色({self.role_id})-权限({self.permission_id}) [{grant_status}]"

    async def save(self, *args, **kwargs):
        """保存关联前执行基础校验，验证通过后调用父类保存方法"""
        if not self.role_id or not self.permission_id:
            raise ValueError("角色ID和权限ID不能为空")
        await self.validate()
        await super().save(*args, **kwargs)

    async def validate(self):
        """验证角色权限关联数据合法性"""
        # 时间逻辑校验
        if self.effective_from and self.effective_to:
            if self.effective_from >= self.effective_to:
                raise ValueError("生效开始时间必须早于结束时间")

        # 自动填充租户ID
        if not self.tenant_id and self.role_id:
            try:
                from azer_common.models.role.model import Role

                role = await Role.objects.filter(id=self.role_id).only("tenant_id").first()
                if not role:
                    raise ValueError(f"角色ID {self.role_id} 不存在")
                self.tenant_id = role.tenant_id
            except Exception as e:
                raise ValueError(f"获取角色租户信息失败: {str(e)}")

    async def soft_delete(self):
        """软删除关联关系，同步标记为未授予"""
        self.is_deleted = True
        self.is_granted = False
        await self.save(update_fields=["is_deleted", "deleted_at", "is_granted"])
        return self

    @property
    def is_expired(self) -> bool:
        """检查权限关联是否过期"""
        now = utc_now()
        if self.effective_to and self.effective_to < now:
            return True
        return False

    @property
    def is_valid(self) -> bool:
        """检查权限关联是否有效（已授予+未过期+未软删除）"""
        if not self.is_granted or self.is_deleted:
            return False
        return not self.is_expired

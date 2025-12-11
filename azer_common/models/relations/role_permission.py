from tortoise import fields
from azer_common.models.base import BaseModel
from azer_common.utils.time import utc_now


class RolePermission(BaseModel):
    # 核心关联字段（修正级联删除策略）
    role = fields.ForeignKeyField(
        'models.Role',
        related_name='role_permissions',
        description='角色',
        on_delete=fields.RESTRICT,
        null=False
    )
    permission = fields.ForeignKeyField(
        'models.Permission',
        related_name='permission_roles',
        description='权限',
        on_delete=fields.RESTRICT,
        null=False
    )

    tenant = fields.ForeignKeyField(
        'models.Tenant',
        related_name='role_permissions',
        description='所属租户（外键，保证数据一致性）',
        on_delete=fields.RESTRICT,
        null=True,  # 兼容全局权限（无租户）
        index=True
    )

    # 状态控制字段
    is_granted = fields.BooleanField(
        default=True,
        description='是否授予'
    )
    effective_from = fields.DatetimeField(
        null=True,
        description='生效开始时间'
    )
    effective_to = fields.DatetimeField(
        null=True,
        description='生效结束时间'
    )
    metadata = fields.JSONField(
        null=True,
        description='扩展元数据'
    )

    class Meta:
        table = "azer_role_permission"
        table_description = '角色权限关联表'
        # 优化唯一约束：保证租户+角色+权限的唯一性（兼容全局权限）
        unique_together = [
            ("role_id", "permission_id", "tenant_id", "is_deleted"),
            ("role_id", "permission_id", "tenant_id")  # 未删除状态下唯一
        ]
        # 优化索引：聚焦高频查询场景
        indexes = [
            ("tenant_id", "role_id", "is_granted", "is_deleted"),  # 租户+角色查有效权限
            ("tenant_id", "permission_id", "is_granted", "is_deleted"),  # 租户+权限查关联角色
            ("is_granted", "effective_to", "is_deleted"),  # 查过期待清理的权限
        ]

    async def save(self, *args, **kwargs):
        """保存前基础校验"""
        if not self.role_id or not self.permission_id:
            raise ValueError("角色ID和权限ID不能为空")
        await self.validate()
        await super().save(*args, **kwargs)

    async def validate(self) -> None:
        """模型层轻量校验"""
        # 1. 时间逻辑校验
        now = utc_now()
        if self.effective_from and self.effective_from > now:
            pass
        if self.effective_from and self.effective_to:
            if self.effective_from >= self.effective_to:
                raise ValueError("生效开始时间必须早于结束时间")
        # 2. 自动填充租户ID
        if not self.tenant_id:
            # 延迟导入避免循环依赖（仅模型层轻量使用）
            from azer_common.models.role.model import Role
            # 仅加载角色租户ID（复杂逻辑抽离到仓储层）
            role = await Role.objects.filter(id=self.role_id).only('tenant_id').first()
            if role:
                self.tenant_id = role.tenant_id

    async def soft_delete(self):
        """重写软删除：同步标记为未授予"""
        self.is_deleted = True
        self.deleted_at = utc_now()
        self.is_granted = False
        await self.save(update_fields=["is_deleted", "deleted_at", "is_granted"])
        return self

    async def activate(self, **kwargs) -> None:
        """重新激活已撤销的权限"""
        if not self.is_granted:
            self.is_granted = True
            await self.save(** kwargs)

    async def revoke(self, **kwargs) -> None:
        """撤销角色权限"""
        self.is_granted = False
        await self.save(** kwargs)

    class PydanticMeta:
        """序列化配置"""
        include = {
            "role": {"id", "code", "name"},
            "permission": {"id", "code", "name"},
            "tenant": {"id", "code", "name"},
        }
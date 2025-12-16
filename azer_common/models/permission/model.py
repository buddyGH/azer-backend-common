from azer_common.models import PUBLIC_APP_LABEL
from tortoise import fields
from azer_common.models.base import BaseModel
from azer_common.utils.validators import validate_permission_code


class Permission(BaseModel):
    """权限定义表，存储细粒度权限规则"""

    # 核心标识字段
    code = fields.CharField(
        max_length=100,
        validators=[validate_permission_code],
        description="权限编码（租户内唯一，如：user:read、article:delete）",
    )
    name = fields.CharField(max_length=50, description="权限显示名称")
    description = fields.CharField(max_length=200, null=True, description="权限详细描述")

    # 关联字段
    tenant = fields.ForeignKeyField(
        model_name=PUBLIC_APP_LABEL + ".Tenant",
        related_name="permissions_list",
        null=True,
        on_delete=fields.RESTRICT,
        description="所属租户（null表示全局权限，所有租户可用）",
    )

    # 权限分类字段
    category = fields.CharField(
        max_length=50, default="general", description="权限分类（如：system、user、content、finance）"
    )
    module = fields.CharField(max_length=50, null=True, description="所属业务模块")

    # 权限规则字段
    action = fields.CharField(max_length=20, description="操作类型（read/write/delete/manage）")
    resource_type = fields.CharField(max_length=50, description="资源类型（如：user、article、order）")
    resource_id = fields.CharField(max_length=100, null=True, description="特定资源ID（为空表示所有资源）")

    # 状态控制字段
    is_enabled = fields.BooleanField(default=True, description="是否启用")
    is_system = fields.BooleanField(default=False, description="是否系统内置权限（不可删除，必须为全局权限）")

    # 扩展字段
    metadata = fields.JSONField(null=True, description="权限扩展元数据")

    class Meta:
        table = "azer_permission"
        table_description = "权限定义表"
        indexes = [
            # 分类+模块查询（权限管理界面）
            ("tenant_id", "category", "module", "is_enabled"),
            # 资源类型+操作查询（权限检查）
            ("tenant_id", "resource_type", "action", "is_enabled"),
            # 编码查询（唯一性检查）
            ("tenant_id", "code", "is_deleted"),
            # 全局权限查询
            ("tenant_id", "is_system", "is_enabled"),
            # 权限搜索优化
            ("code", "name", "tenant_id"),
        ]
        unique_together = ("code", "tenant_id", "is_deleted")

    class PydanticMeta:
        include = {
            "roles": {"id", "code", "name"},
            "tenant": {"id", "code", "name"},
        }

    def __str__(self):
        """权限实例的字符串表示，兼容租户未加载场景"""
        try:
            tenant_id = self.tenant_id
            tenant_info = "[全局]" if tenant_id is None else f"[租户:{tenant_id}]"
        except Exception:
            tenant_info = "[租户:未知]"
        return f"{tenant_info} {self.code}: {self.name}"

    async def save(self, *args, **kwargs):
        """保存权限前执行数据验证，验证通过后调用父类保存方法"""
        await self.validate()
        await super().save(*args, **kwargs)

    async def validate(self):
        """验证权限数据合法性"""
        # 系统权限校验
        if self.is_system and self.tenant_id is not None:
            raise ValueError("系统内置权限必须为全局权限（tenant_id需为空）")

        # 编码格式校验
        validate_permission_code(self.code)

        # 唯一性校验
        query = self.__class__.all_objects.filter(code=self.code, is_deleted=False)
        if self.tenant_id is None:
            query = query.filter(tenant_id__isnull=True)
        else:
            query = query.filter(tenant_id=self.tenant_id)
        if self.id:
            query = query.exclude(id=self.id)

        existing = await query.first()
        if existing:
            tenant_desc = "全局" if existing.tenant_id is None else f"租户 {existing.tenant_id}"
            raise ValueError(f"{tenant_desc}下已存在相同权限编码: {self.code}")

    async def soft_delete(self):
        """软删除权限，系统权限禁止删除"""
        if self.is_system:
            raise ValueError("系统内置权限不允许删除")
        self.is_deleted = True
        self.is_enabled = False
        await self.save(update_fields=["is_deleted", "deleted_at", "is_enabled"])
        return self

    async def enable(self):
        """启用权限"""
        self.is_enabled = True
        await self.save(update_fields=["is_enabled", "updated_at"])

    async def disable(self):
        """禁用权限"""
        if self.is_system:
            raise ValueError("系统内置权限不允许禁用")
        self.is_enabled = False
        await self.save(update_fields=["is_enabled", "updated_at"])

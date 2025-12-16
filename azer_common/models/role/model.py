from tortoise import fields
from azer_common.models.base import BaseModel
from azer_common.utils.validators import validate_role_code
from azer_common.models import PUBLIC_APP_LABEL


class Role(BaseModel):
    """角色表，多租户场景下的角色定义，支持权限继承"""

    # 核心标识字段
    code = fields.CharField(
        max_length=50,
        validators=[validate_role_code],
        description="角色编码（租户内唯一，大写字母/数字/下划线，以字母/下划线开头）",
    )
    name = fields.CharField(max_length=50, description="角色显示名称")
    role_type = fields.CharField(
        max_length=50, null=True, description="角色类型（业务自定义分类，如：管理员/运营/普通用户）"
    )
    description = fields.CharField(max_length=200, null=True, description="角色详细描述")

    # 多租户关联字段
    tenant = fields.ForeignKeyField(
        model_name=PUBLIC_APP_LABEL + ".Tenant",
        related_name="roles",
        on_delete=fields.RESTRICT,
        description="所属租户（强关联，非空）",
        index=True,
        null=False,
    )

    # 系统控制字段
    is_system = fields.BooleanField(
        default=False, description="是否系统内置角色（不可删除、设置父角色、标记为默认角色）"
    )
    is_default = fields.BooleanField(default=False, description="是否默认角色（新用户自动分配）")
    is_enabled = fields.BooleanField(default=True, description="角色是否启用（禁用后关联权限自动失效）")

    # 权限继承字段
    level = fields.IntField(default=0, ge=0, description="角色等级（用于权限继承，数值越高优先级越高）")
    parent = fields.ForeignKeyField(
        model_name=PUBLIC_APP_LABEL + ".Role",
        related_name="children",
        null=True,
        on_delete=fields.SET_NULL,
        description="父角色（用于权限继承，需同租户）",
    )

    # 扩展字段
    metadata = fields.JSONField(null=True, description="角色扩展元数据")

    class Meta:
        table = "azer_role"
        table_description = "角色表（多租户+权限继承）"
        ordering = ["level", "code"]
        unique_together = [("tenant_id", "code", "is_deleted")]
        indexes = [
            ("tenant_id", "parent_id"),
            ("tenant_id", "is_default"),
            ("tenant_id", "is_enabled", "is_deleted"),
            ("level", "tenant_id"),
            ("tenant_id", "code", "is_deleted"),
            ("tenant_id", "role_type", "is_enabled"),
            ("tenant_id", "level", "is_enabled"),
        ]

    class PydanticMeta:
        include = {
            "tenant": {"id", "code", "name"},
            "permissions": {"id", "code", "name"},
            "parent": {"id", "code", "name"},
            "children": {"id", "code", "name"},
        }

    def __str__(self):
        """角色实例的字符串表示，兼容租户未加载场景"""
        try:
            tenant_code = self.tenant.code if self.tenant else self.tenant_id
        except Exception:
            tenant_code = self.tenant_id
        return f"[{tenant_code}] {self.code} ({self.name})"

    async def save(self, *args, **kwargs):
        """保存角色前执行数据验证，验证通过后调用父类保存方法"""
        await self.validate()
        await super().save(*args, **kwargs)

    async def validate(self):
        """验证角色数据合法性"""
        # 基础非空校验
        if self.tenant_id is None:
            raise ValueError("角色必须归属具体租户（tenant_id 不能为空）")

        # 编码格式校验
        validate_role_code(self.code)

        # 自引用校验
        if self.parent_id == self.id:
            raise ValueError("父角色不能是当前角色本身")

        # 系统角色校验
        if self.is_system:
            if self.parent_id:
                raise ValueError("系统内置角色不允许设置父角色")
            if self.is_default:
                raise ValueError("系统内置角色不能同时为默认角色")

        # 层级校验
        if self.level < 0:
            raise ValueError("角色等级不能为负数（level >= 0）")

    async def soft_delete(self):
        """软删除角色，系统角色禁止删除"""
        if self.is_system:
            raise ValueError("系统内置角色不允许删除")
        self.is_deleted = True
        self.is_enabled = False
        await self.save(update_fields=["is_deleted", "deleted_at", "is_enabled"])
        return self

    async def enable(self):
        """启用角色"""
        self.is_enabled = True
        await self.save(update_fields=["is_enabled", "updated_at"])

    async def disable(self):
        """禁用角色"""
        if self.is_system:
            raise ValueError("系统内置角色不允许禁用")
        self.is_enabled = False
        await self.save(update_fields=["is_enabled", "updated_at"])

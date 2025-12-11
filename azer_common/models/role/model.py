import re
from tortoise import fields
from azer_common.models.base import BaseModel


class Role(BaseModel):
    # 核心标识字段
    code = fields.CharField(
        max_length=50,
        description='角色代码（同一租户下唯一）'
    )
    name = fields.CharField(
        max_length=50,
        description='角色显示名称'
    )
    role_type = fields.CharField(
        max_length=50,
        null=True,
        default=None,
        description='角色类型（业务自定义分类，如：管理员/运营/普通用户）'
    )
    description = fields.CharField(
        max_length=200,
        null=True,
        description='角色描述'
    )

    # 多租户字段
    tenant = fields.ForeignKeyField(
        'models.Tenant',
        related_name='roles',
        on_delete=fields.RESTRICT,
        description='所属租户（强关联，非空）',
        index=True,
        null=False
    )
    # 多对多关系
    permissions = fields.ManyToManyField(
        'models.Permission',
        through='azer_role_permission',
        related_name='roles',
        description='角色关联的权限',
        forward_key='role_id',
        backward_key='permission_id',
    )

    # 系统控制字段
    is_system = fields.BooleanField(
        default=False,
        description='是否系统内置角色（不可删除/修改核心属性）'
    )
    is_default = fields.BooleanField(
        default=False,
        description='是否默认角色（新用户自动分配）'
    )
    is_enabled = fields.BooleanField(
        default=True,
        description='角色是否启用（禁用后关联权限自动失效）'
    )

    # 权限继承字段
    level = fields.IntField(
        default=0,
        ge=0,
        description='角色等级（用于权限继承，数值越高优先级越高）'
    )
    parent = fields.ForeignKeyField(
        'models.Role',
        related_name='children',
        null=True,
        on_delete=fields.SET_NULL,
        description='父角色（用于角色继承）'
    )
    # 扩展字段
    metadata = fields.JSONField(
        null=True,
        description='角色元数据（如扩展属性、备注等）'
    )

    class Meta:
        table = "azer_role"
        table_description = '角色表（多租户+权限继承）'
        ordering = ["level", "code"]
        indexes = [
            ("tenant_id", "parent_id"),
            ("tenant_id", "is_default"),
            ("tenant_id", "is_enabled", "is_deleted"),
            ("level", "tenant_id"),
        ]
        unique_together = [
            ("tenant_id", "code", "is_deleted"),
        ]

    def __str__(self):
        """优化：处理租户未加载的边界情况"""
        try:
            tenant_code = self.tenant.code if self.tenant else self.tenant_id
        except Exception:
            tenant_code = self.tenant_id
        return f"[{tenant_code}] {self.code} ({self.name})"

    async def save(self, *args, **kwargs):
        """保存前验证（强化租户+逻辑校验）"""
        await self.validate()
        await super().save(*args, **kwargs)

    async def validate(self):
        # 1. 基础非空/格式校验
        if self.tenant_id is None:
            raise ValueError("角色必须归属具体租户（tenant_id 不能为空）")
        if not re.match(r'^[A-Z_][A-Z0-9_]{0,49}$', self.code):
            raise ValueError("角色代码格式错误")
        # 2. 自引用校验
        if self.parent_id == self.id:
            raise ValueError("父角色不能是当前角色本身")
        # 3. 系统角色校验
        if self.is_system:
            if self.parent_id:
                raise ValueError("系统内置角色不允许设置父角色")
            if self.is_default:
                raise ValueError("系统内置角色不能同时为默认角色")
        # 4. 层级校验
        if self.level < 0:
            raise ValueError("角色等级不能为负数（level >= 0）")

    async def soft_delete(self):
        if self.is_system:
            raise ValueError("系统内置角色不允许删除")
        self.is_deleted = True
        self.is_enabled = False
        await self.save(update_fields=["is_deleted", "deleted_at", "is_enabled"])
        return self

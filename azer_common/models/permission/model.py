import re
from typing import List, Optional, Union
from azer_common.models.base import BaseModel
from tortoise import fields
from tortoise.expressions import Q
from azer_common.utils.validators import validate_permission_code


class Permission(BaseModel):
    # 权限标识
    code = fields.CharField(
        max_length=100,
        validators=[validate_permission_code],
        description='权限代码（租户内唯一标识），如：user:read, article:delete'
    )
    name = fields.CharField(
        max_length=50,
        description='权限显示名称'
    )
    description = fields.CharField(
        max_length=200,
        null=True,
        description='权限详细描述'
    )

    roles = fields.ManyToManyField(
        'models.Role',
        through='azer_role_permission',
        related_name='permissions',
        description='拥有该权限的角色',
    )

    tenant = fields.ForeignKeyField(
        'models.Tenant',
        related_name='permissions_list',
        null=True,  # null=全局权限，所有租户可用
        on_delete=fields.RESTRICT,
        description='所属租户（null表示全局权限）'
    )

    # 权限分类
    category = fields.CharField(
        max_length=50,
        default='general',
        description='权限分类，如：system, user, content, finance'
    )
    module = fields.CharField(
        max_length=50,
        null=True,
        description='所属模块'
    )

    # 权限元数据
    action = fields.CharField(
        max_length=20,
        description='操作类型：read, write, delete, manage'
    )
    resource_type = fields.CharField(
        max_length=50,
        description='资源类型'
    )
    resource_id = fields.CharField(
        max_length=100,
        null=True,
        description='特定资源ID（为空表示所有资源）'
    )

    # 状态控制
    is_enabled = fields.BooleanField(
        default=True,
        description='是否启用'
    )
    is_system = fields.BooleanField(
        default=False,
        description='是否系统内置权限'
    )

    metadata = fields.JSONField(
        null=True,
        description='扩展元数据'
    )

    class Meta:
        table = "azer_permission"
        table_description = '权限定义表'
        indexes = [
            ("category", "module"),
            ("resource_type", "action"),
            ("code", "is_enabled", "tenant_id"),  # 优化：核心查询索引
            ("tenant_id", "category", "is_enabled"),  # 新增：按租户+分类查询
        ]
        unique_together = ("code", "tenant_id", "is_deleted")  # 租户+编码+未删除 唯一

    def __str__(self):
        """优化：处理tenant未加载的边界情况，统一租户ID类型"""
        try:
            # 优先用tenant_id（无需加载关联），兼容tenant未加载场景
            tenant_id = self.tenant_id
            tenant_info = "[全局]" if tenant_id is None else f"[租户:{tenant_id}]"
        except Exception:
            tenant_info = "[租户:未知]"
        return f"{tenant_info} {self.code}: {self.name}"

    async def save(self, *args, **kwargs):
        """保存前验证"""
        await self.validate()
        await super().save(*args, **kwargs)

    async def validate(self):
        """验证权限数据（强化逻辑+类型校验）"""
        # 1. 系统权限必须是全局权限（tenant_id为null）
        if self.is_system and self.tenant_id is not None:
            raise ValueError("系统内置权限必须为全局权限（tenant_id需为空）")

        # 2. 代码格式验证（强化正则）
        if not re.match(r'^[a-z_][a-z0-9_:]{0,99}$', self.code):
            raise ValueError(
                "权限代码必须为小写字母、数字、下划线和冒号，"
                "以字母或下划线开头，长度不超过100个字符"
            )

        # 3. 唯一性验证（排除软删除的，区分全局/租户）
        query = self.__class__.objects.filter(
            code=self.code,
            is_deleted=False  # 补充：排除软删除的记录
        )
        # 区分全局/租户：tenant_id 相同 或 都为 null
        if self.tenant_id is None:
            query = query.filter(tenant_id__isnull=True)
        else:
            query = query.filter(tenant_id=self.tenant_id)

        # 排除自身（更新场景）
        if self.id:
            query = query.exclude(id=self.id)

        existing = await query.first()
        if existing:
            tenant_desc = "全局" if existing.tenant_id is None else f"租户 {existing.tenant_id}"
            raise ValueError(f"{tenant_desc}下已存在相同权限代码: {self.code}")

    async def soft_delete(self):
        if self.is_system:
            raise ValueError("系统内置角色不允许删除")
        self.is_deleted = True
        self.is_enabled = False
        await self.save(update_fields=["is_deleted", "deleted_at", "is_enabled"])
        return self

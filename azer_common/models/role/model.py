import re
from tortoise import fields
from azer_common.models.base import BaseModel
from azer_common.models.enums.base import RoleEnum
from azer_common.models.relations.role_permission import RolePermission


class Role(BaseModel):
    code = fields.CharField(
        max_length=50,
        unique=True,
        description='角色代码（唯一标识）'
    )
    name = fields.CharField(
        max_length=50,
        description='角色显示名称'
    )
    role_type = fields.CharEnumField(
        enum_type=RoleEnum,
        description='角色类型（对应原name字段）'
    )
    description = fields.CharField(
        max_length=200,
        null=True,
        description='角色描述'
    )
    is_system = fields.BooleanField(
        default=False,
        description='是否系统内置角色（不可删除）'
    )
    is_default = fields.BooleanField(
        default=False,
        description='是否默认角色（新用户自动分配）'
    )
    level = fields.IntField(
        default=0,
        description='角色等级（用于权限继承）'
    )
    permissions = fields.ManyToManyField(
        'models.Permission',
        related_name='roles',
        through='azer_role_permission',
        description='角色权限'
    )
    parent = fields.ForeignKeyField(
        'models.Role',
        related_name='children',
        null=True,
        on_delete=fields.SET_NULL,
        description='父角色（用于角色继承）'
    )
    metadata = fields.JSONField(
        null=True,
        description='角色元数据'
    )

    class Meta:
        table = "azer_role"
        table_description = '角色表'
        ordering = ["level", "code"]
        indexes = [
            ("is_system", "is_default"),
            ("level",),
        ]

    async def save(self, *args, **kwargs):
        """保存前验证"""
        await self.validate()
        await super().save(*args, **kwargs)

    async def validate(self):
        """验证角色数据"""
        # 1. 检查角色代码格式
        if not re.match(r'^[A-Z_][A-Z0-9_]*$', self.code):
            raise ValueError("角色代码必须为大写字母、数字和下划线，且以字母或下划线开头")

        # 2. 检查父角色不能是自己
        if self.parent and self.parent.id == self.id:
            raise ValueError("父角色不能是自己")

        # 3. 检查层级循环
        if self.parent:
            current = self.parent
            while current:
                if current.id == self.id:
                    raise ValueError("检测到角色层级循环")
                current = current.parent

        # 4. 系统角色验证
        if self.is_system:
            # 系统角色不能有父角色（避免复杂的权限继承）
            if self.parent:
                raise ValueError("系统角色不能设置父角色")

    async def delete(self, using_db=None, pk=None):
        if self.is_system:
            raise ValueError("系统内置角色不允许物理删除")
        await super().delete(using_db=using_db)

    async def grant_permission(
            self,
            permission,
            granted_by=None,
            effective_from=None,
            effective_to=None,
            reason=None,
            metadata=None,
    ):
        """为角色授予权限（便捷方法）"""
        return await RolePermission.grant(
            role=self,
            permission=permission,
            granted_by=granted_by,
            effective_from=effective_from,
            effective_to=effective_to,
            reason=reason,
            metadata=metadata,
        )

    async def revoke_permission(
            self,
            permission,
            revoked_by=None,
            reason=None,
    ):
        """撤销角色的权限（便捷方法）"""
        role_perm = await RolePermission.find_by_role_and_permission(
            role_id=self.id,
            permission_id=permission.id if hasattr(permission, 'id') else permission,
        )

        if role_perm:
            await role_perm.revoke(revoked_by=revoked_by, reason=reason)
            return True

        return False

    async def get_effective_permissions(self, check_time=None):
        """获取角色的有效权限（便捷方法）"""
        return await RolePermission.get_effective_permissions(
            role_id=self.id,
            check_time=check_time,
        )

    async def has_permission(self, permission_code, check_time=None):
        """检查角色是否拥有权限（便捷方法）"""
        return await RolePermission.has_permission(
            role_id=self.id,
            permission_code=permission_code,
            check_time=check_time,
        )

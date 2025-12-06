from datetime import timedelta

from tortoise import fields, models


class Permission(models.Model):
    id = fields.IntField(pk=True)
    code = fields.IntField(unique=True, description='权限码（位图形式）')
    name = fields.CharField(unique=True, max_length=50, description='权限名称')  # 权限标识符
    description = fields.CharField(max_length=200, null=True, blank=True, description='权限描述')  # 权限描述
    permission_type = fields.CharField(max_length=20, null=True, blank=True, description='权限类型')  # 权限类型
    is_purchasable = fields.BooleanField(default=False, description='是否需要购买')  # 是否需要单独购买
    price = fields.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, description='购买价格')  # 购买价格（如果有）
    currency = fields.CharField(max_length=10, default='RMB', description='货币类型')
    is_active = fields.BooleanField(default=True, description='权限是否启用')  # 权限是否启用
    is_deleted = fields.BooleanField(default=False, description='是否已删除（软删除）')  # 是否已删除
    duration = fields.BigIntField(null=True, blank=True, description='持续时间（如果有），例如30天')
    granted_at = fields.DatetimeField(auto_now_add=True, description='授予时间')
    updated_at = fields.DatetimeField(auto_now=True, description='更新时间')
    expires_at = fields.DatetimeField(null=True, blank=True, description='过期时间（如果有）')

    # 自动计算 expires_at
    async def save(self, *args, **kwargs):
        if self.duration and not self.granted_at:
            self.granted_at = fields.DatetimeField().now()

        if self.duration:
            self.expires_at = self.granted_at + timedelta(seconds=self.duration)
        else:
            self.expires_at = None

        if self.expires_at and self.expires_at <= fields.DatetimeField().now():
            self.is_active = False
            self.is_deleted = True

        if self.is_deleted:
            self.is_active = False

        await super().save(*args, **kwargs)

    class Meta:
        table = "azer_permission"
        indexes = [
            ("is_active", "is_deleted"),  # 新增复合索引，加速 is_active 和 is_deleted 过滤
            ("expires_at",),  # 单独的 expires_at 索引，加速过期时间相关查询
        ]
        table_description = '权限定义表'


class RolePermission(models.Model):
    role = fields.ForeignKeyField('models.Role', related_name='permissions', description='角色')
    permission = fields.ForeignKeyField('models.Permission', related_name='role_permissions', description='权限')

    class Meta:
        table = "azer_role_permission"
        unique_together = ("role", "permission")
        table_description = '角色权限关联表'


class UserAdditionalPermission(models.Model):
    user = fields.ForeignKeyField('models.User', related_name='additional_permissions', description='用户')
    permission = fields.ForeignKeyField('models.Permission', related_name='user_permissions', description='附加权限')

    class Meta:
        table = "azer_user_add_permission"
        unique_together = ("user", "permission")
        table_description = '用户附加权限表'


class PermissionHistory(models.Model):
    permission = fields.ForeignKeyField('models.Permission', related_name='history', description='关联权限')
    change_type = fields.CharField(max_length=50, description='变更类型',
                                   choices=['GRANTED', 'REVOKED', 'EXPIRED', 'UPDATED', 'DELETED'])
    changed_by = fields.CharField(max_length=50, description='变更用户id或系统')
    change_reason = fields.CharField(max_length=200, null=True, blank=True, description='变更原因')
    changed_at = fields.DatetimeField(auto_now_add=True, description='变更时间')

    class Meta:
        table = "azer_permission_history"
        table_description = '权限变更历史表'

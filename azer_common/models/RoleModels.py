from tortoise import fields, models

from azer_common.models.enums import RoleEnum


class Role(models.Model):
    """
        Role类表示应用系统中的角色模型，通过tortoise-orm进行持久化管理。

        属性:
            id: 整数类型，主键，自增。
            name: 枚举类型，角色名称，唯一，最大长度为20个字符。
            description: 字符类型，最大长度200，可为空，角色描述。
    """
    id = fields.IntField(pk=True)
    name = fields.CharEnumField(enum_type=RoleEnum, unique=True, max_length=20, description='角色名')
    description = fields.CharField(max_length=200, null=True, blank=True, description='角色描述')

    class Meta:
        table = "azer_role"
        table_description = '角色表'


class UserRole(models.Model):
    """
        class UserRole(models.Model):
            用户角色关系表，其中包含关于用户和角色关联的信息。

            user:
                fields.ForeignKeyField('models.User', related_name='user_roles', description='用户', on_delete=fields.NO_ACTION)
                用户信息，引用 User 表，禁用级联删除。

            role:
                fields.ForeignKeyField('models.Role', related_name='role_users', description='角色', on_delete=fields.NO_ACTION)
                角色信息，引用 Role 表，禁用级联删除。

            granted_by:
                fields.ForeignKeyField('models.User', related_name='granted_roles', null=True, description='授予该角色的用户（为空则表示系统分配）', on_delete=fields.NO_ACTION)
                授予角色的用户（即谁分配的角色），可以为空，如果为空则表示是系统分配的角色，禁用级联删除。

            granted_at:
                fields.DatetimeField(auto_now_add=True, description='授予时间')
                角色授予的时间，自动记录为创建记录的时间。

            duration:
                fields.BigIntField(null=True, description='持续时间，为空则表示无限期')
                角色分配的持续时间，可以为空，如果为空则表示无限期。

            class Meta:
                unique_together = ("user", "role")
                table = "azer_user_role"
                table_description = '用户角色关系表'
                设定唯一性约束，保证每个用户和角色的组合是唯一的，指定表名，同时提供表描述。
    """
    user = fields.ForeignKeyField('models.User',
                                  related_name='user_roles',
                                  description='用户',
                                  on_delete=fields.NO_ACTION,  # 禁用级联删除
    )
    role = fields.ForeignKeyField('models.Role',
                                  related_name='role_users',
                                  description='角色',
                                  on_delete=fields.NO_ACTION
                                  )
    granted_by = fields.ForeignKeyField('models.User',
                                        related_name='granted_roles',
                                        null=True,
                                        description='授予该角色的用户（为空则表示系统分配）',
                                        on_delete=fields.NO_ACTION
                                        )
    granted_at = fields.DatetimeField(auto_now_add=True, description='授予时间')
    duration = fields.BigIntField(null=True, description='持续时间，为空则表示无限期')

    class Meta:
        table = "azer_user_role"
        unique_together = ("user", "role")
        table_description = '用户角色关系表'
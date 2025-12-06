import re
import uuid

import argon2.exceptions
from argon2 import PasswordHasher
from tortoise import fields, models
from tortoise.signals import pre_save

from azer_common.models.enums import SexEnum
from azer_common.utils.validators import validate_email, validate_mobile, validate_password, validate_username


class User(models.Model):
    """
    这是一个用户模型类，用于定义用户信息和操作。

    类属性:
        id (UUIDField): 用户的唯一标识符，默认生成UUID。
        username (CharField): 用户名，长度不超过50个字符，必须唯一。包含自定义验证规则。
        password (CharField): 用户密码，长度不超过128个字符。
        nick_name (CharField): 用户昵称，长度不超过20个字符，默认为“unknown”。
        email (CharField): 用户邮箱，长度不超过50个字符，必须唯一。包含自定义验证规则。
        mobile (CharField): 用户手机号，长度恰好为11个字符，必须唯一。包含自定义验证规则。
        sex (CharEnumField): 用户性别，使用SexEnum枚举类型，默认为SexEnum.OTHER。
        avatar (CharField): 用户头像，长度不超过255个字符，默认为“avatar/default.jpg”。
        desc (TextField): 用户个人简介，最长512个字符，默认为空字符串。
        home_path (CharField): 用户个人主页，长度不超过200个字符，默认为空字符串。
        roles (ManyToManyField): 用户角色，多对多关联到Role模型，通过UserRole类关联。

    方法:
        set_password(password):
            设置用户密码。

            参数:
                password (str): 新的用户密码。

            异常:
                当密码验证失败时抛出ValidationError。
        verify_password(password):
            验证用户密码。

            参数:
                password (str): 要验证的密码。

            返回:
                bool: 如果密码匹配则返回True，否则返回False。
    """
    id = fields.UUIDField(pk=True, default=uuid.uuid4)
    username = fields.CharField(max_length=50, unique=True, validators=[validate_username], description='用户名')
    password = fields.CharField(max_length=128, description='密码', null=False)
    nick_name = fields.CharField(max_length=20, default='unknown', null=True, description='昵称')
    full_name = fields.CharField(max_length=20, null=True, description="用户全名")
    identity_card = fields.CharField(max_length=18, null=True, description="身份证号")
    email = fields.CharField(max_length=50, null=True, unique=True, validators=[validate_email], default=None,
                             description='邮箱')
    mobile = fields.CharField(max_length=11, null=True, unique=True, validators=[validate_mobile], default=None,
                              description='手机号')
    sex = fields.CharField(enum_type=SexEnum, default=SexEnum.OTHER, max_length=10, description='性别')
    avatar = fields.CharField(max_length=200, default='avatar/default.jpg', null=True, description='头像')
    desc = fields.CharField(max_length=200, default='', null=True, description='个人简介')
    home_path = fields.CharField(max_length=200, default='', null=True, description='个人主页')

    roles = fields.ManyToManyField('models.Role', related_name='users', through='models.UserRole', description='用户角色')

    class Meta:
        table = "azer_user"
        table_description = '用户表'

    def set_password(self, password):
        validate_password(password)
        ph = PasswordHasher()
        self.password = ph.hash(password)

    def verify_password(self, password):
        ph = PasswordHasher()
        try:
            return ph.verify(self.password, password)
        except argon2.exceptions.VerifyMismatchError:
            return False


def is_password_hashed(password):
    """
    :param password: 用于检测是否为哈希的密码字符串
    :return: 如果密码是 argon2 哈希格式则返回 True，否则返回 False
    """
    # 正则表达式匹配 bcrypt 哈希前缀
    return re.match(r'^\$argon2[did]\$', password)


@pre_save(User)
async def hash_user_password(sender, instance, using_db, update_fields):
    """
    :param sender: 触发信号的模型类。
    :param instance: 当前操作的模型实例，通常是即将保存到数据库的对象。
    :param using_db: 数据库别名，用于区分使用哪个数据库。
    :param update_fields: 一个包含需要更新的字段名称的集合，或 None 表示更新所有字段。
    :return: None
    """
    # 检查密码是否已经加密，bcrypt的哈希结果通常是以'$2a$'、'$2b$'、'$2y$'开头
    # 使用封装好的函数检查密码是否已经哈希过
    if not is_password_hashed(instance.password):
        instance.set_password(instance.password)

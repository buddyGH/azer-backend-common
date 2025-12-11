# azer_common/models/user/model.py
from typing import Optional
from tortoise import fields
from azer_common.models.base import BaseModel
from azer_common.models.enums.base import SexEnum, UserStatusEnum
from azer_common.utils.time import today
from azer_common.utils.validators import (
    validate_url, validate_username, validate_email,
    validate_mobile, validate_identity_card
)


class User(BaseModel):
    """用户表 - 存储用户核心信息和业务状态"""
    # 账户信息
    username = fields.CharField(
        max_length=30,
        unique=True,
        validators=[validate_username],
        description='用户名',
        index=True
    )

    # 账户状态
    status = fields.CharEnumField(
        UserStatusEnum,
        default=UserStatusEnum.UNVERIFIED,
        description='用户核心状态'
    )

    # 个人身份信息
    real_name = fields.CharField(
        max_length=30,
        null=True,
        description="用户全名"
    )
    identity_card = fields.CharField(
        max_length=18,
        null=True,
        unique=True,
        validators=[validate_identity_card],
        description="身份证号",
        index=True
    )

    # 联系信息
    email = fields.CharField(
        max_length=100,
        null=True,
        unique=True,
        validators=[validate_email],
        description='邮箱',
        index=True
    )
    mobile = fields.CharField(
        max_length=15,
        null=True,
        unique=True,
        validators=[validate_mobile],
        description='手机号',
        index=True
    )

    # 用户资料
    nick_name = fields.CharField(
        max_length=50,
        null=True,
        description='昵称'
    )
    sex = fields.CharEnumField(
        SexEnum,
        default=SexEnum.OTHER,
        description='性别'
    )
    birth_date = fields.DateField(
        null=True,
        description='出生日期'
    )
    avatar = fields.CharField(
        max_length=500,
        null=True,
        validators=[validate_url],
        description='头像URL'
    )
    desc = fields.TextField(
        null=True,
        description='个人简介'
    )
    home_path = fields.CharField(
        max_length=500,
        null=True,
        description='个人主页路径'
    )
    preferences = fields.JSONField(
        null=True,
        description='用户偏好设置',
        default=dict
    )

    # 关系字段
    roles = fields.ManyToManyField(
        'models.Role',
        related_name='users',
        through='azer_user_role',
        description='用户角色'
    )

    tenants = fields.ManyToManyField(
        'models.Tenant',
        related_name='users',
        through='azer_tenant_user',
        description='用户属于多个租户'
    )

    class Meta:
        table = "azer_user"
        table_description = '用户表'
        indexes = [
            ("status", "created_at"),
        ]

    def __str__(self) -> str:
        """用户友好的字符串表示"""
        return f"{self.username} ({self.real_name or self.nick_name})"

    # 便捷属性访问
    @property
    def is_active(self) -> bool:
        """检查用户是否处于活跃状态"""
        return self.status == UserStatusEnum.ACTIVE

    @property
    def display_name(self) -> str:
        """获取显示名称（优先顺序）"""
        return self.real_name or self.nick_name or self.username

    @property
    def age(self) -> Optional[int]:
        """计算年龄"""
        if not self.birth_date:
            return None
        _today = today()
        return _today.year - self.birth_date.year - (
                (_today.month, _today.day) < (self.birth_date.month, self.birth_date.day)
        )

    # 用户偏好便捷方法
    def get_preference(self, key: str, default=None):
        """安全获取用户偏好设置"""
        return self.preferences.get(key, default) if self.preferences else default

    def set_preference(self, key: str, value):
        """安全设置用户偏好"""
        if not self.preferences:
            self.preferences = {}
        self.preferences[key] = value


# 导入信号
import azer_common.models.user.signals
# azer_common/models/user/model.py
from datetime import datetime, timedelta
from typing import Dict, Optional
from async_property import async_property
from tortoise import fields
from azer_common.models.auth.model import UserCredential
from azer_common.models.base import BaseModel
from azer_common.models.types.enums import SexEnum, UserLifecycleStatus, UserSecurityStatus
from azer_common.utils.time import today_utc
from azer_common.utils.validators import (
    validate_url,
    validate_username,
    validate_email,
    validate_mobile,
    validate_identity_card,
)


class User(BaseModel):
    """用户表 - 存储用户核心信息和业务状态"""

    # 账户信息
    username = fields.CharField(
        max_length=30, unique=True, validators=[validate_username], description="用户名", index=True
    )

    # 用户认证凭证
    credential: fields.ReverseRelation[UserCredential]

    # 账户状态
    status = fields.CharEnumField(
        UserLifecycleStatus, default=UserLifecycleStatus.UNVERIFIED, description="用户生命周期状态"
    )

    security_status = fields.CharEnumField(UserSecurityStatus, null=True, description="安全限制状态（冻结/封禁等）")
    # 状态相关时间戳
    activated_at = fields.DatetimeField(null=True, description="激活时间")
    last_active_at = fields.DatetimeField(null=True, description="最后活跃时间")
    frozen_at = fields.DatetimeField(null=True, description="冻结时间")
    banned_at = fields.DatetimeField(null=True, description="封禁时间")
    closed_at = fields.DatetimeField(null=True, description="注销时间")

    # 个人身份信息
    real_name = fields.CharField(max_length=30, null=True, description="用户全名")
    identity_card = fields.CharField(
        max_length=18, null=True, unique=True, validators=[validate_identity_card], description="身份证号", index=True
    )

    # 联系信息
    email = fields.CharField(
        max_length=100, null=True, unique=True, validators=[validate_email], description="邮箱", index=True
    )
    mobile = fields.CharField(
        max_length=15, null=True, unique=True, validators=[validate_mobile], description="手机号", index=True
    )

    # 用户资料
    is_system = fields.BooleanField(default=False, description="是否系统内置用户（不可删除）")
    nick_name = fields.CharField(max_length=50, null=True, description="昵称")
    sex = fields.CharEnumField(SexEnum, default=SexEnum.OTHER, description="性别")
    birth_date = fields.DateField(null=True, description="出生日期")
    avatar = fields.CharField(max_length=500, null=True, validators=[validate_url], description="头像URL")
    desc = fields.TextField(null=True, description="个人简介")
    home_path = fields.CharField(max_length=500, null=True, description="个人主页路径")
    preferences = fields.JSONField(null=True, description="用户偏好设置", default=dict)

    class Meta:
        table = "azer_user"
        table_description = "用户表"
        indexes = [
            ("status", "created_at"),
            # 多微服务场景下，频繁查询活跃用户
            ("status", "last_active_at", "is_deleted"),
            # 用户搜索优化
            ("username", "is_deleted"),
            ("email", "is_deleted"),
            ("mobile", "is_deleted"),
            # 身份验证相关
            ("identity_card", "is_deleted"),
        ]

    def __str__(self) -> str:
        """用户友好的字符串表示"""
        return f"{self.username} ({self.real_name or self.nick_name})"

    # 便捷属性访问
    @property
    def is_active(self) -> bool:
        """检查用户是否处于活跃状态"""
        return self.status == UserLifecycleStatus.ACTIVE and self.security_status is None

    @property
    def is_blocked(self) -> bool:
        """用户是否被阻止"""
        return self.security_status is not None

    @property
    def display_name(self) -> str:
        """获取显示名称（优先顺序）"""
        return self.real_name or self.nick_name or self.username

    @property
    def age(self) -> Optional[int]:
        """计算年龄"""
        if not self.birth_date:
            return None
        _today = today_utc()
        return (
            _today.year
            - self.birth_date.year
            - ((_today.month, _today.day) < (self.birth_date.month, self.birth_date.day))
        )

    @property
    def days_since_last_active(self) -> Optional[int]:
        """距离上次活跃的天数"""
        duration = self.get_status_duration("last_active")
        return duration.days if duration else None

    @property
    def days_since_frozen(self) -> Optional[int]:
        """冻结天数"""
        if not self.frozen_at:
            return None
        duration = self.get_status_duration("frozen")
        return duration.days if duration else None

    @property
    def days_since_banned(self) -> Optional[int]:
        """封禁天数"""
        if not self.banned_at:
            return None
        duration = self.get_status_duration("banned")
        return duration.days if duration else None

    @property
    def days_since_activated(self) -> Optional[int]:
        """激活天数"""
        if not self.activated_at:
            return None
        duration = self.get_status_duration("activated")
        return duration.days if duration else None

    @async_property
    async def credential(self) -> Optional[UserCredential]:
        """
        异步属性：获取当前用户关联的认证凭证（OneToOne关联）
        调用：await user.credential
        """
        try:
            return await self.credential.first()
        except Exception:
            return None

    # 状态时间戳便捷方法
    def get_status_timestamp(self, status_type: str) -> Optional[datetime]:
        """
        获取状态对应的时间戳
        :param status_type: 状态类型，可选值: activated, last_active, frozen, banned, closed
        :return: 对应的时间戳或None
        """
        timestamps = {
            "activated": self.activated_at,
            "last_active": self.last_active_at,
            "frozen": self.frozen_at,
            "banned": self.banned_at,
            "closed": self.closed_at,
        }
        return timestamps.get(status_type)

    def get_all_status_timestamps(self) -> Dict[str, Optional[datetime]]:
        """获取所有状态时间戳的字典"""
        return {
            "activated": self.activated_at,
            "last_active": self.last_active_at,
            "frozen": self.frozen_at,
            "banned": self.banned_at,
            "closed": self.closed_at,
            "created": self.created_at,
            "updated": self.updated_at,
        }

    def get_status_duration(self, status_type: str) -> Optional[timedelta]:
        """
        获取状态持续时长
        :param status_type: 状态类型
        :return: 持续时长或None
        """
        from azer_common.utils.time import utc_now

        timestamp = self.get_status_timestamp(status_type)
        if not timestamp:
            return None

        return utc_now() - timestamp

    # 用户偏好便捷方法
    def get_preference(self, key: str, default=None):
        """安全获取用户偏好设置"""
        return self.preferences.get(key, default) if self.preferences else default

    def set_preference(self, key: str, value):
        """安全设置用户偏好"""
        if not self.preferences:
            self.preferences = {}
        self.preferences[key] = value

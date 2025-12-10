from enum import Enum


# 注意:必须继承str
class SexEnum(str, Enum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


class UserStatusEnum(str, Enum):
    """用户基础状态 - 反映账户可用性
    备注：LOCKED（锁定）状态移至 Redis 中临时存储和处理，不纳入核心状态枚举
    """
    # 正常状态
    UNVERIFIED = "unverified"  # 未验证
    PENDING = "pending"        # 审核中
    ACTIVE = "active"          # 正常使用

    # 异常状态（移除 LOCKED）
    FROZEN = "frozen"          # 冻结（暂时无法使用，该状态需要人工转换）

    # 结束状态
    INACTIVE = "inactive"      # 不活跃（长时间未登录）
    BANNED = "banned"          # 永久封禁
    CLOSED = "closed"          # 已注销


class MFATypeEnum(str, Enum):
    """MFA类型枚举"""
    NONE = "none"  # 未启用
    TOTP = "totp"  # 基于时间的动态口令（如Google Authenticator）
    SMS = "sms"  # 短信验证码
    EMAIL = "email"  # 邮箱验证码


class RoleEnum(str, Enum):
    GUEST = "guest"  # 游客
    USER = "user"  # 用户
    MEMBER = "vip"  # 会员
    SUPER_MEMBER = "svip"  # 超级会员
    ADMIN = "admin"  # 管理员
    SUPER_ADMIN = "super_admin"  # 系统管理员
    DEVELOPER = "developer"  # 开发者
    SYSTEM = "system"  # 系统

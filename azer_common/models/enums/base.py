from enum import Enum


# 注意:必须继承str
class SexEnum(str, Enum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


class UserLifecycleStatus(str, Enum):
    """用户生命周期状态 - 核心状态"""

    UNVERIFIED = "unverified"  # 未验证
    PENDING = "pending"  # 待审核（需要人工介入）
    ACTIVE = "active"  # 正常活跃
    INACTIVE = "inactive"  # 不活跃（自动触发）
    CLOSED = "closed"  # 已注销（用户主动）


class UserSecurityStatus(str, Enum):
    """用户安全状态 - 临时/风控状态"""

    FROZEN = "frozen"  # 风控冻结（临时）
    SUSPENDED = "suspended"  # 管理员暂停
    BANNED = "banned"  # 永久封禁


class MFATypeEnum(str, Enum):
    """MFA类型枚举"""

    NONE = "none"  # 未启用
    TOTP = "totp"  # 基于时间的动态口令（如Google Authenticator）
    SMS = "sms"  # 短信验证码
    EMAIL = "email"  # 邮箱验证码


class RolePermissionOperationType(str, Enum):
    """权限关联操作类型枚举"""

    GRANT = "GRANT"  # 授予权限
    REVOKE = "REVOKE"  # 撤销权限
    ACTIVATE = "ACTIVATE"  # 激活权限
    UPDATE_EFFECTIVE = "UPDATE_EFFECTIVE"  # 更新生效时间
    CLEANUP_EXPIRED = "CLEANUP_EXPIRED"  # 自动清理过期权限


class UserRoleOperationType(str, Enum):
    """用户角色操作类型枚举"""

    GRANT = "GRANT"  # 授予角色
    REVOKE = "REVOKE"  # 撤销角色
    RENEW = "RENEW"  # 续期角色
    ACTIVATE = "ACTIVATE"  # 重新激活角色
    CLEANUP_EXPIRED = "CLEANUP_EXPIRED"  # 自动清理过期角色

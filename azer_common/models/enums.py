from enum import Enum


# 注意:必须继承str
class SexEnum(str, Enum):
    """
    性别枚举类，用于表示不同的性别选项。

    枚举成员:
        MALE: 表示男性性别。
        FEMALE: 表示女性性别。
        OTHER: 表示其他性别。
    """
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


class RoleEnum(str, Enum):
    """
    RoleEnum 枚举类定义了系统中的各种角色

    GUEST:
        游客
    USER:
        用户
    MEMBER:
        会员
    SUPER_MEMBER:
        超级会员
    ADMIN:
        管理员
    SUPER_ADMIN:
        系统管理员
    DEVELOPER:
        开发者
    SYSTEM:
        系统
    """
    GUEST = "guest"  # 游客
    USER = "user"  # 用户
    MEMBER = "vip"  # 会员
    SUPER_MEMBER = "svip"  # 超级会员
    ADMIN = "admin"  # 管理员
    SUPER_ADMIN = "super_admin"  # 系统管理员
    DEVELOPER = "developer"  # 开发者
    SYSTEM = "system"  # 系统

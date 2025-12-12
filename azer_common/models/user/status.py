# azer_common/models/user/status.py
from azer_common.models.enums.base import UserLifecycleStatus


class UserLifecycleStatusTransitions:
    """用户生命周期状态转换规则"""

    ALLOWED_TRANSITIONS = {
        UserLifecycleStatus.UNVERIFIED: {
            UserLifecycleStatus.ACTIVE,   # 验证通过
            UserLifecycleStatus.PENDING,  # 需要审核
            UserLifecycleStatus.CLOSED,   # 用户放弃注册
        },
        UserLifecycleStatus.PENDING: {
            UserLifecycleStatus.ACTIVE,   # 审核通过
            UserLifecycleStatus.CLOSED,   # 审核不通过或用户撤销
        },
        UserLifecycleStatus.ACTIVE: {
            UserLifecycleStatus.INACTIVE,  # 变为不活跃
            UserLifecycleStatus.CLOSED,    # 用户主动注销
        },
        UserLifecycleStatus.INACTIVE: {
            UserLifecycleStatus.ACTIVE,    # 重新激活
            UserLifecycleStatus.CLOSED,    # 系统自动注销（长期不活跃）
        },
        UserLifecycleStatus.CLOSED: {
            # 注销不可逆，除非特殊恢复流程
        },
    }

    @classmethod
    def can_transition(cls, from_status: UserLifecycleStatus, to_status: UserLifecycleStatus) -> bool:
        if from_status == to_status:
            return False

        allowed = cls.ALLOWED_TRANSITIONS.get(from_status, set())
        return to_status in allowed

    @classmethod
    def get_allowed_transitions(cls, current_status: UserLifecycleStatus) -> set:
        return cls.ALLOWED_TRANSITIONS.get(current_status, set()).copy()
from azer_common.models.enums.base import UserStatusEnum


# TODO: 核心态放 User，凭证态放 UserCredential，临时态拆到多业务表（如审核 / 验证 / 风控）使用独立状态机服务
class UserStatusTransitions:
    """用户状态转换规则"""

    # 允许的状态转换
    ALLOWED_TRANSITIONS = {
        # ========== 初始流程 ==========
        UserStatusEnum.UNVERIFIED: {
            UserStatusEnum.ACTIVE,  # 验证通过
            UserStatusEnum.PENDING,  # 需要审核
            UserStatusEnum.CLOSED,  # 用户放弃注册
        },

        UserStatusEnum.PENDING: {
            UserStatusEnum.ACTIVE,  # 审核通过
            UserStatusEnum.FROZEN,  # 审核拒绝（冻结）
            UserStatusEnum.BANNED,  # 审核拒绝（封禁-恶意）
            UserStatusEnum.CLOSED,  # 审核不通过/用户撤销
        },

        # ========== 正常流程 ==========
        UserStatusEnum.ACTIVE: {
            UserStatusEnum.FROZEN,  # 风控冻结
            UserStatusEnum.INACTIVE,  # 变为不活跃
            UserStatusEnum.CLOSED,  # 用户主动注销
            UserStatusEnum.BANNED,  # 严重违规封禁
            UserStatusEnum.PENDING,  # 重新审核（资料变更）
        },

        UserStatusEnum.INACTIVE: {
            UserStatusEnum.ACTIVE,  # 重新激活
            UserStatusEnum.CLOSED,  # 系统自动注销（长期不活跃）
        },

        # ========== 异常流程 ==========
        UserStatusEnum.FROZEN: {
            UserStatusEnum.ACTIVE,  # 解冻（调查后无问题）
            UserStatusEnum.BANNED,  # 转为封禁（确认违规）
            UserStatusEnum.PENDING,  # 需要重新审核
        },

        # ========== 结束流程 ==========
        UserStatusEnum.BANNED: {
            # 封禁通常是最终状态，但允许特殊情况
            UserStatusEnum.CLOSED,  # 注销封禁账户（清理）
            # 解封：需特殊流程，不在常规转换中
        },

        UserStatusEnum.CLOSED: {
            # 注销不可逆，除非特殊恢复流程
            # UserStatusEnum.ACTIVE,  # 特殊恢复（需额外逻辑）
        },
    }

    # # 特殊流程（需要额外权限/审核）
    # SPECIAL_TRANSITIONS = {
    #     # 解封
    #     (UserStatusEnum.BANNED, UserStatusEnum.ACTIVE): {
    #         "description": "解封",
    #         "required_role": "admin",  # 需要管理员
    #         "needs_approval": True,  # 需要审核
    #         "reason_required": True,  # 需要理由
    #     },
    #
    #     # 恢复已注销账户
    #     (UserStatusEnum.CLOSED, UserStatusEnum.ACTIVE): {
    #         "description": "恢复账户",
    #         "required_role": "admin",
    #         "needs_approval": True,
    #         "reason_required": True,
    #         "time_limit": 30,  # 30天内可恢复
    #     },
    # }

    @classmethod
    def can_transition(cls, from_status: UserStatusEnum, to_status: UserStatusEnum) -> bool:
        """检查常规状态转换是否允许"""
        if from_status == to_status:
            return False

        # 新用户创建
        if from_status is None:
            return to_status in {UserStatusEnum.UNVERIFIED, UserStatusEnum.PENDING}

        # 检查常规转换
        allowed = cls.ALLOWED_TRANSITIONS.get(from_status, set())
        return to_status in allowed

    @classmethod
    def get_allowed_transitions(cls, current_status: UserStatusEnum) -> set:
        """获取当前状态允许的所有转换"""
        if current_status is None:
            return {UserStatusEnum.UNVERIFIED, UserStatusEnum.PENDING}

        return cls.ALLOWED_TRANSITIONS.get(current_status, set()).copy()

    # @classmethod
    # def get_special_transition_info(cls, from_status: UserStatusEnum, to_status: UserStatusEnum) -> dict:
    #     """获取特殊转换信息"""
    #     return cls.SPECIAL_TRANSITIONS.get((from_status, to_status), {})

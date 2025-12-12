# azer_common/repositories/user/components/stats.py
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from tortoise.expressions import Function, Q, F
from tortoise.functions import Count
from azer_common.models.enums.base import SexEnum, UserLifecycleStatus, UserSecurityStatus
from azer_common.repositories.base_component import BaseComponent
from azer_common.utils.time import utc_now
from tortoise.expressions import RawSQL
from pypika_tortoise.terms import Function as PypikaFunction


class PypikaExtract(PypikaFunction):
    """
    对应 PostgreSQL EXTRACT(field FROM source) 函数。
    参数：field - 要提取的部分，如 'hour', 'year', 'month' 等
         source - 时间字段或表达式
    """

    def __init__(self, field: str, source):
        super().__init__("EXTRACT", field, "FROM", source)


# 2. 自定义 Tortoise ORM 函数
class Extract(Function):
    """
    用于 Tortoise ORM 查询的 Extract 函数包装器。
    使用示例：Extract('hour', F('last_active_at'))
    """
    database_func = PypikaExtract


class ExtractHour(Extract):
    """专门提取小时的便捷类"""

    def __init__(self, source_field):
        super().__init__('hour', source_field)


class UserStatsComponent(BaseComponent):

    async def count_users_by_status(
            self,
            tenant_id: Optional[str] = None
    ) -> Dict[str, int]:
        """
        按状态统计用户数量
        :param tenant_id: 租户ID
        :return: 状态统计字典
        """
        query = self.model.filter(is_deleted=False)

        if tenant_id:
            query = query.filter(tenants__id=tenant_id)

        # 生命周期状态统计
        lifecycle_stats = {}
        for status in UserLifecycleStatus:
            count = await query.filter(status=status).count()
            lifecycle_stats[status.value] = count

        # 安全状态统计
        security_stats = {}
        for status in UserSecurityStatus:
            count = await query.filter(security_status=status).count()
            security_stats[status.value] = count

        # 活跃用户统计（ACTIVE且无安全限制）
        active_count = await query.filter(
            status=UserLifecycleStatus.ACTIVE,
            security_status__isnull=True
        ).count()

        return {
            "lifecycle": lifecycle_stats,
            "security": security_stats,
            "active": active_count,
            "total": sum(lifecycle_stats.values())
        }

    async def count_by_status(
            self,
            tenant_id: Optional[str] = None,
            include_deleted: bool = False
    ) -> Dict[UserLifecycleStatus, int]:
        """
        按生命周期状态统计用户数量
        :param tenant_id: 租户ID（可选）
        :param include_deleted: 是否包含软删除用户
        :return: 状态-数量映射字典
        """
        query = self.model.all()
        if not include_deleted:
            query = query.filter(is_deleted=False)
        if tenant_id:
            query = query.filter(tenants__id=tenant_id)

        # 分组统计
        stats = await query.annotate(
            status_value=F("status")
        ).group_by("status").values("status").annotate(count=Count("id"))

        # 转换为枚举映射
        result = {status: 0 for status in UserLifecycleStatus}
        for item in stats:
            status = UserLifecycleStatus(item["status"])
            result[status] = item["count"]

        return result

    async def count_by_gender(
            self,
            tenant_id: Optional[str] = None,
            status: Optional[UserLifecycleStatus] = None,
            include_deleted: bool = False
    ) -> Dict[SexEnum, int]:
        """
        按性别统计用户数量
        :param tenant_id: 租户ID（可选）
        :param status: 生命周期状态过滤（可选）
        :param include_deleted: 是否包含软删除用户
        :return: 性别-数量映射字典
        """
        query = self.model.all()
        if not include_deleted:
            query = query.filter(is_deleted=False)
        if tenant_id:
            query = query.filter(tenants__id=tenant_id)
        if status:
            query = query.filter(status=status)

        # 分组统计（包含None值）
        stats = await query.annotate(
            gender_value=F("gender")
        ).group_by("gender").values("gender").annotate(count=Count("id"))

        # 转换为枚举映射
        result = {gender: 0 for gender in SexEnum}
        result[None] = 0  # 未设置性别的用户
        for item in stats:
            gender_val = item["gender"]
            if gender_val is None:
                result[None] = item["count"]
            else:
                gender = SexEnum(gender_val)
                result[gender] = item["count"]

        return result

    async def count_by_age_range(
            self,
            age_ranges: List[Tuple[int, Optional[int]]],
            tenant_id: Optional[str] = None,
            status: Optional[UserLifecycleStatus] = None,
            include_deleted: bool = False
    ) -> Dict[str, int]:
        """
        按年龄区间统计用户数量
        :param age_ranges: 年龄区间列表，示例：[(0,18), (18,25), (25, None)]
        :param tenant_id: 租户ID（可选）
        :param status: 生命周期状态过滤（可选）
        :param include_deleted: 是否包含软删除用户
        :return: 区间描述-数量映射字典
        """
        query = self.model.filter(
            birth_date__isnull=False,
            is_deleted=False if not include_deleted else True
        )

        # 附加过滤条件
        if tenant_id:
            query = query.filter(tenants__id=tenant_id)
        if status:
            query = query.filter(status=status)

        # 计算所有用户年龄
        users = await query.values("id", "birth_date")
        age_count = {f"{start}-{end or '+'}": 0 for start, end in age_ranges}

        today = utc_now().date()
        for user in users:
            birth_date = user["birth_date"]
            age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))

            # 匹配年龄区间
            for start, end in age_ranges:
                range_key = f"{start}-{end or '+'}"
                if end is None:
                    if age >= start:
                        age_count[range_key] += 1
                        break
                else:
                    if start <= age < end:
                        age_count[range_key] += 1
                        break

        return age_count

    async def get_user_statistics(self, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """
        获取用户整体统计数据
        :param tenant_id: 租户ID（可选）
        :return: 统计字典
        """
        # 构建基础查询条件
        base_filters = {"is_deleted": False}
        if tenant_id:
            base_filters["tenant_id"] = tenant_id

        # 1. 基础数量统计
        status_count = await self.count_by_status(tenant_id=tenant_id)
        gender_count = await self.count_by_gender(tenant_id=tenant_id)

        # 2. 安全状态统计
        query = self.model.filter(**base_filters)

        security_stats = await query.annotate(
            sec_status=F("security_status")
        ).group_by("security_status").values("security_status").annotate(count=Count("id"))

        security_count = {status: 0 for status in UserSecurityStatus}
        security_count[None] = 0  # 无安全限制
        for item in security_stats:
            sec_val = item["security_status"]
            if sec_val is None:
                security_count[None] = item["count"]
            else:
                try:
                    security_count[UserSecurityStatus(sec_val)] = item["count"]
                except ValueError:
                    # 处理可能的无效枚举值
                    security_count[None] = security_count.get(None, 0) + item["count"]

        # 3. 活跃/非活跃统计
        active_filters = {**base_filters, "status": UserLifecycleStatus.ACTIVE}
        inactive_filters = {**base_filters, "status": UserLifecycleStatus.INACTIVE}

        active_users_count = await self.model.filter(**active_filters).count()
        inactive_users_count = await self.model.filter(**inactive_filters).count()

        # 4. 新增用户统计（今日/昨日/7天/30天）
        today = utc_now().date()
        yesterday = today - timedelta(days=1)

        # 今日新增
        new_today_filters = {**base_filters, "created_at__date": today}
        new_today = await self.model.filter(**new_today_filters).count()

        # 昨日新增
        new_yesterday_filters = {**base_filters, "created_at__date": yesterday}
        new_yesterday = await self.model.filter(**new_yesterday_filters).count()

        # 近7天新增
        new_7d_filters = {**base_filters, "created_at__gte": utc_now() - timedelta(days=7)}
        new_7d = await self.model.filter(**new_7d_filters).count()

        # 近30天新增
        new_30d_filters = {**base_filters, "created_at__gte": utc_now() - timedelta(days=30)}
        new_30d = await self.model.filter(**new_30d_filters).count()

        return {
            "total_users": sum(status_count.values()),
            "status_distribution": {k.value: v for k, v in status_count.items()},
            "security_distribution": {k.value if k else "none": v for k, v in security_count.items()},
            "gender_distribution": {k.value if k else "unknown": v for k, v in gender_count.items()},
            "active_users": active_users_count,
            "inactive_users": inactive_users_count,
            "new_users": {
                "today": new_today,
                "yesterday": new_yesterday,
                "7d": new_7d,
                "30d": new_30d
            }
        }

    async def get_user_growth_by_period(
            self,
            start_date: datetime,
            end_date: datetime,
            group_by: str = "day"
    ) -> List[Dict]:
        """
        按时间段统计用户增长趋势
        :param start_date: 开始时间
        :param end_date: 结束时间
        :param group_by: 分组维度（day/week/month）
        :return: 增长趋势列表（含时间段、新增数量、累计数量）
        """
        if group_by not in ["day", "week", "month"]:
            raise ValueError("group_by 仅支持 day/week/month")

        # 构建时间分组表达式
        if group_by == "day":
            date_format = "YYYY-MM-DD"
            sql_format = "'%Y-%m-%d'"
        elif group_by == "week":
            date_format = "YYYY-WW"
            sql_format = "'%Y-%W'"
        else:  # month
            date_format = "YYYY-MM"
            sql_format = "'%Y-%m'"

        # 创建原始 SQL 表达式
        period_expr = RawSQL(f"strftime({sql_format}, created_at)")

        # 筛选指定时间段内创建的用户
        query = self.model.filter(
            created_at__gte=start_date,
            created_at__lte=end_date,
            is_deleted=False
        )

        # 使用 annotate 和 values 进行分组统计
        growth_data = await query.annotate(
            period=period_expr
        ).group_by('period').values('period').annotate(
            new_count=Count('id')
        ).order_by('period')

        # 计算累计数量
        cumulative = 0
        result = []
        for item in growth_data:
            cumulative += item["new_count"]
            result.append({
                "period": item["period"],
                "new_users": item["new_count"],
                "cumulative_users": cumulative
            })

        return result

    async def get_user_activity_report(self, tenant_id: Optional[str] = None, days: int = 30) -> Dict[str, Any]:
        """
        获取用户活跃度报告（近N天）
        :param tenant_id: 租户ID（可选）
        :param days: 统计天数（默认30天）
        :return: 活跃度报告字典
        """
        if days <= 0:
            raise ValueError("days 必须大于0")

        # 基础时间范围
        end_date = utc_now()
        start_date = end_date - timedelta(days=days)

        # 构建基础查询条件
        base_filters = {"is_deleted": False, "status": UserLifecycleStatus.ACTIVE}
        if tenant_id:
            base_filters["tenant_id"] = tenant_id

        # 1. 活跃用户统计（按最后活跃时间分层）
        # 获取在指定时间段内有活跃的用户
        active_users_query = self.model.filter(
            last_active_at__gte=start_date,
            **base_filters
        )

        active_users = await active_users_query.all()

        # 分层统计：高活跃(最后活跃在7天内)、中活跃(8-15天)、低活跃(16-30天)
        high_active = 0
        mid_active = 0
        low_active = 0

        today = utc_now()
        for user in active_users:
            if not user.last_active_at:
                # 如果没有最后活跃时间，跳过或归为低活跃
                low_active += 1
                continue

            # 计算距离今天的天数
            days_since_active = (today - user.last_active_at).days

            if days_since_active <= 7:
                high_active += 1
            elif days_since_active <= 15:
                mid_active += 1
            else:
                low_active += 1

        # 2. 新增用户留存率计算（简化版）
        # 注意：实际留存率计算需要更复杂的数据跟踪
        # 这里使用简化方法：统计30天前新增的用户，并检查他们是否在后续有活跃

        # 30天前的新增用户
        thirty_days_ago = end_date - timedelta(days=30)
        new_users_30d_ago = await self.model.filter(
            created_at__date=thirty_days_ago.date(),
            **base_filters
        ).values_list("id", flat=True)

        total_new = len(new_users_30d_ago)

        if total_new > 0:
            # 次日留存：新增后第二天有活跃
            next_day = thirty_days_ago + timedelta(days=1)
            retained_1d = await self.model.filter(
                id__in=new_users_30d_ago,
                last_active_at__date=next_day.date()
            ).count()

            # 7日留存：新增后7天内有活跃
            seven_days_later = thirty_days_ago + timedelta(days=7)
            retained_7d = await self.model.filter(
                id__in=new_users_30d_ago,
                last_active_at__gte=thirty_days_ago,
                last_active_at__lte=seven_days_later
            ).count()

            # 30日留存：新增后30天内有活跃
            retained_30d = await self.model.filter(
                id__in=new_users_30d_ago,
                last_active_at__gte=thirty_days_ago,
                last_active_at__lte=end_date
            ).count()

            retention_1d = (retained_1d / total_new) * 100
            retention_7d = (retained_7d / total_new) * 100
            retention_30d = (retained_30d / total_new) * 100
        else:
            retention_1d = retention_7d = retention_30d = 0

        # 3. 活跃时段分布（按小时）
        # 获取近30天活跃用户的小时分布
        hour_stats_query = self.model.filter(
            last_active_at__gte=end_date - timedelta(days=30),
            **base_filters
        )

        # 注意：这里假设数据库支持hour函数，具体语法可能因数据库而异
        hour_stats = await hour_stats_query.annotate(
            hour=ExtractHour("last_active_at")
        ).group_by("hour").values("hour").annotate(count=Count("id"))

        hour_distribution = {f"{h:02d}:00": 0 for h in range(24)}
        for item in hour_stats:
            hour = item["hour"]
            hour_distribution[f"{hour:02d}:00"] = item["count"]

        # 4. 非活跃用户数量（30天内无活跃）
        inactive_users_count = await self.model.filter(
            **base_filters
        ).filter(
            Q(last_active_at__lt=start_date) | Q(last_active_at__isnull=True)
        ).count()

        return {
            "report_period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "days": days
            },
            "active_user_distribution": {
                "high_active": high_active,  # 7天内活跃
                "mid_active": mid_active,  # 8-15天活跃
                "low_active": low_active,  # 16-30天活跃
                "total_active": len(active_users)
            },
            "retention_rate": {
                "new_users_count": total_new,
                "1d_retention": round(retention_1d, 2),
                "7d_retention": round(retention_7d, 2),
                "30d_retention": round(retention_30d, 2)
            },
            "active_hour_distribution": hour_distribution,
            "inactive_users_count": inactive_users_count,
            "inactive_users_percentage": round(
                (inactive_users_count / max(len(active_users) + inactive_users_count, 1)) * 100, 2
            ) if (len(active_users) + inactive_users_count) > 0 else 0
        }

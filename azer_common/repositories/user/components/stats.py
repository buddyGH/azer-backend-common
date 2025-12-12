# azer_common/repositories/user/components/stats.py
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from tortoise.expressions import Q, F
from tortoise.functions import Count
from azer_common.models.enums.base import SexEnum, UserLifecycleStatus, UserSecurityStatus
from azer_common.repositories.base_component import BaseComponent
from azer_common.utils.time import utc_now


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
        # 1. 基础数量统计
        status_count = await self.count_by_status(tenant_id=tenant_id)
        gender_count = await self.count_by_gender(tenant_id=tenant_id)

        # 2. 安全状态统计
        security_stats = await self.model.filter(
            is_deleted=False
        ).annotate(
            sec_status=F("security_status")
        ).group_by("security_status").values("security_status").annotate(count=Count("id"))

        security_count = {status: 0 for status in UserSecurityStatus}
        security_count[None] = 0  # 无安全限制
        for item in security_stats:
            sec_val = item["security_status"]
            if sec_val is None:
                security_count[None] = item["count"]
            else:
                security_count[UserSecurityStatus(sec_val)] = item["count"]

        # 3. 活跃/非活跃统计
        active_users, _ = await self.get_active_users(tenant_id=tenant_id, limit=0)
        inactive_users, _ = await self.get_inactive_users(tenant_id=tenant_id, limit=0)

        # 4. 新增用户（今日/昨日/7天/30天）
        today = utc_now().date()
        yesterday = today - timedelta(days=1)
        seven_days_ago = today - timedelta(days=7)
        thirty_days_ago = today - timedelta(days=30)

        new_today = await self.model.filter(
            created_at__date=today,
            is_deleted=False
        ).filter(tenants__id=tenant_id if tenant_id else Q(tenants__id__isnull=True)).count()

        new_yesterday = await self.model.filter(
            created_at__date=yesterday,
            is_deleted=False
        ).filter(tenants__id=tenant_id if tenant_id else Q(tenants__id__isnull=True)).count()

        new_7d = await self.model.filter(
            created_at__gte=utc_now() - timedelta(days=7),
            is_deleted=False
        ).filter(tenants__id=tenant_id if tenant_id else Q(tenants__id__isnull=True)).count()

        new_30d = await self.model.filter(
            created_at__gte=utc_now() - timedelta(days=30),
            is_deleted=False
        ).filter(tenants__id=tenant_id if tenant_id else Q(tenants__id__isnull=True)).count()

        return {
            "total_users": sum(status_count.values()),
            "status_distribution": {k.value: v for k, v in status_count.items()},
            "security_distribution": {k.value if k else "none": v for k, v in security_count.items()},
            "gender_distribution": {k.value if k else "unknown": v for k, v in gender_count.items()},
            "active_users": len(active_users),
            "inactive_users": len(inactive_users),
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
        elif group_by == "week":
            date_format = "YYYY-WW"
        else:  # month
            date_format = "YYYY-MM"

        # 筛选指定时间段内创建的用户
        query = self.model.filter(
            created_at__gte=start_date,
            created_at__lte=end_date,
            is_deleted=False
        ).annotate(
            period=F("created_at__strftime", date_format)
        ).group_by("period").values("period").annotate(new_count=Count("id"))

        # 按时间段排序
        growth_data = sorted(await query, key=lambda x: x["period"])

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
        thirty_days_ago = end_date - timedelta(days=30)

        # 1. 活跃用户统计（按活跃天数分层）
        active_users = await self.model.filter(
            last_active_at__gte=start_date,
            is_deleted=False,
            status=UserLifecycleStatus.ACTIVE,
            security_status__isnull=True
        ).filter(tenants__id=tenant_id if tenant_id else Q(tenants__id__isnull=True)).all()

        # 分层统计：高活跃(≥15天)、中活跃(5-14天)、低活跃(1-4天)
        high_active = 0
        mid_active = 0
        low_active = 0

        today = utc_now().date()
        for user in active_users:
            if not user.last_active_at:
                continue

            # 计算近30天活跃天数（简化版：按last_active_at距离今天的天数）
            active_days = (today - user.last_active_at.date()).days
            if active_days <= 15:
                high_active += 1
            elif active_days <= 25:
                mid_active += 1
            else:
                low_active += 1

        # 2. 新增用户留存率（次日/7日/30日）
        # 新增用户（30天前至29天前）
        new_users_30d_ago = await self.model.filter(
            created_at__gte=thirty_days_ago - timedelta(days=1),
            created_at__lt=thirty_days_ago,
            is_deleted=False
        ).filter(tenants__id=tenant_id if tenant_id else Q(tenants__id__isnull=True)).values_list("id", flat=True)

        # 次日留存（新增后1天内有活跃）
        retained_1d = await self.model.filter(
            id__in=new_users_30d_ago,
            last_active_at__gte=thirty_days_ago,
            last_active_at__lt=thirty_days_ago + timedelta(days=1)
        ).count()

        # 7日留存
        retained_7d = await self.model.filter(
            id__in=new_users_30d_ago,
            last_active_at__gte=thirty_days_ago + timedelta(days=6)
        ).count()

        # 30日留存
        retained_30d = await self.model.filter(
            id__in=new_users_30d_ago,
            last_active_at__gte=end_date - timedelta(days=1)
        ).count()

        # 计算留存率
        total_new = len(new_users_30d_ago)
        retention_1d = (retained_1d / total_new) * 100 if total_new > 0 else 0
        retention_7d = (retained_7d / total_new) * 100 if total_new > 0 else 0
        retention_30d = (retained_30d / total_new) * 100 if total_new > 0 else 0

        # 3. 活跃时段分布（按小时）
        hour_stats = await self.model.filter(
            last_active_at__gte=start_date,
            is_deleted=False
        ).filter(tenants__id=tenant_id if tenant_id else Q(tenants__id__isnull=True)).annotate(
            hour=F("last_active_at__hour")
        ).group_by("hour").values("hour").annotate(count=Count("id"))

        hour_distribution = {str(h): 0 for h in range(24)}
        for item in hour_stats:
            hour_distribution[str(item["hour"])] = item["count"]

        return {
            "report_period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "days": days
            },
            "active_user分层": {
                "high_active": high_active,  # ≥15天活跃
                "mid_active": mid_active,  # 5-14天活跃
                "low_active": low_active,  # 1-4天活跃
                "total_active": len(active_users)
            },
            "retention_rate": {
                "new_users_count": total_new,
                "1d": round(retention_1d, 2),
                "7d": round(retention_7d, 2),
                "30d": round(retention_30d, 2)
            },
            "active_hour_distribution": hour_distribution,
            "inactive_users_count": await self.get_inactive_users(tenant_id=tenant_id, limit=0)[1]
        }

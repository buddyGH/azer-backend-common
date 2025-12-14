from datetime import datetime, timedelta, timezone
from typing import Optional, Union

# 定义UTC时区常量
UTC = timezone.utc
# 本地时区（可根据服务部署环境调整，或通过配置中心注入）
LOCAL_TZ = datetime.now(timezone.utc).astimezone().tzinfo


def utc_now() -> datetime:
    """生成带UTC时区的当前时间（精确到秒）"""
    return datetime.now(UTC).replace(microsecond=0)


def today_utc() -> datetime:
    """生成UTC时区的今日0点整（datetime类型）"""
    return utc_now().replace(hour=0, minute=0, second=0, microsecond=0)


def today_local() -> datetime:
    """生成本地时区的今日0点整（datetime类型）"""
    return datetime.now(LOCAL_TZ).replace(hour=0, minute=0, second=0, microsecond=0)


def add_days(days: int, base_time: Optional[datetime] = None) -> datetime:
    """
    给指定时间添加天数（默认基于UTC当前时间）
    :param days: 要添加的天数（负数表示减去）
    :param base_time: 基准时间，不传则用utc_now()
    :return: 计算后的UTC时区时间
    """
    if base_time is None:
        base_time = utc_now()
    # 先标准化基准时间为UTC，再计算
    normalized_base = normalize_datetime(base_time)
    return normalized_base + timedelta(days=days)


def add_hours(hours: int, base_time: Optional[datetime] = None) -> datetime:
    """给指定时间添加小时数（默认基于UTC当前时间）"""
    if base_time is None:
        base_time = utc_now()
    normalized_base = normalize_datetime(base_time)
    return normalized_base + timedelta(hours=hours)


def add_minutes(minutes: int, base_time: Optional[datetime] = None) -> datetime:
    """给指定时间添加分钟数（默认基于UTC当前时间）"""
    if base_time is None:
        base_time = utc_now()
    normalized_base = normalize_datetime(base_time)
    return normalized_base + timedelta(minutes=minutes)


def normalize_datetime(dt: datetime) -> datetime:
    """
    标准化时间：统一转换为UTC时区，并忽略微秒
    :param dt: 任意时区/无时区的datetime
    :return: UTC时区、无微秒的datetime
    """
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        # 无时区的时间，默认视为UTC
        dt = dt.replace(tzinfo=UTC)
    else:
        # 转换为UTC时区
        dt = dt.astimezone(UTC)
    return dt.replace(microsecond=0)


def to_iso_string(dt: datetime) -> str:
    """
    将datetime转换为ISO 8601格式字符串（UTC时区，如：2025-12-13T10:00:00Z）
    适配FastAPI接口返回、日志记录、跨服务调用场景
    """
    normalized_dt = normalize_datetime(dt)
    return normalized_dt.isoformat().replace("+00:00", "Z")


def from_iso_string(iso_str: str) -> datetime:
    """
    从ISO 8601字符串解析为UTC时区的datetime
    兼容带Z/不带Z、带+00:00的格式
    """
    # 替换Z为+00:00，兼容解析
    iso_str = iso_str.replace("Z", "+00:00")
    dt = datetime.fromisoformat(iso_str)
    return normalize_datetime(dt)


def timestamp_to_datetime(timestamp: Union[int, float], is_milliseconds: bool = False) -> datetime:
    """
    时间戳转换为UTC时区的datetime
    :param timestamp: 时间戳（整数/浮点数）
    :param is_milliseconds: 是否为毫秒级时间戳（前端常用）
    :return: UTC时区的datetime
    """
    if is_milliseconds:
        timestamp = timestamp / 1000
    dt = datetime.fromtimestamp(timestamp, tz=UTC)
    return normalize_datetime(dt)


def datetime_to_timestamp(dt: datetime, is_milliseconds: bool = False) -> Union[int, float]:
    """
    将datetime转换为时间戳
    :param dt: 任意时区的datetime
    :param is_milliseconds: 是否返回毫秒级时间戳
    :return: 秒级/毫秒级时间戳
    """
    normalized_dt = normalize_datetime(dt)
    timestamp = normalized_dt.timestamp()
    if is_milliseconds:
        return int(timestamp * 1000)
    return int(timestamp)


def get_start_of_day(dt: Optional[datetime] = None, tz: timezone = UTC) -> datetime:
    """
    获取指定时间所在天的开始时间（00:00:00）
    :param dt: 基准时间，不传则用当前时区的当前时间
    :param tz: 目标时区
    :return: 当天0点的datetime
    """
    if dt is None:
        dt = datetime.now(tz)
    else:
        dt = dt.astimezone(tz)
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def get_end_of_day(dt: Optional[datetime] = None, tz: timezone = UTC) -> datetime:
    """
    获取指定时间所在天的结束时间（23:59:59）
    :param dt: 基准时间，不传则用当前时区的当前时间
    :param tz: 目标时区
    :return: 当天23:59:59的datetime
    """
    if dt is None:
        dt = datetime.now(tz)
    else:
        dt = dt.astimezone(tz)
    return dt.replace(hour=23, minute=59, second=59, microsecond=0)


def is_between(
    check_dt: datetime,
    start_dt: datetime,
    end_dt: datetime,
    inclusive: bool = True,
) -> bool:
    """
    判断时间是否在指定区间内
    :param check_dt: 要检查的时间
    :param start_dt: 区间开始时间
    :param end_dt: 区间结束时间
    :param inclusive: 是否包含边界（start <= check <= end）
    :return: 是否在区间内
    """
    norm_check = normalize_datetime(check_dt)
    norm_start = normalize_datetime(start_dt)
    norm_end = normalize_datetime(end_dt)

    if inclusive:
        return norm_start <= norm_check <= norm_end
    return norm_start < norm_check < norm_end


def to_local_timezone(dt: datetime) -> datetime:
    """将UTC时间转换为本地时区时间"""
    normalized_dt = normalize_datetime(dt)
    return normalized_dt.astimezone(LOCAL_TZ)

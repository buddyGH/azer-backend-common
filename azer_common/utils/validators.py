import re
from datetime import datetime
from typing import List


# 验证用户名的格式
def validate_username(value: str):
    """用户名格式验证：4-30位，允许字母、数字、点、下划线或@符号"""
    if not re.match(r"^[A-Za-z0-9_.@]{4,30}$", value):
        raise ValueError("用户名格式无效，应为4到30位的字母、数字、点、下划线或@符号。")


# 验证邮箱格式
def validate_email(value: str):
    """邮箱格式验证"""
    if not re.match(
        r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*\.[a-zA-Z]{2,}$",
        value,
    ):
        raise ValueError("邮箱格式无效，请输入正确的邮箱地址。")


# 验证手机号码格式（中国手机号）
def validate_mobile(value: str):
    """中国大陆手机号验证"""
    if not re.match(r"^(13[0-9]|14[5|7]|15[0-9]|18[0-9]|17[0-9])\d{8}$", value):
        raise ValueError("手机号格式无效，请输入有效的中国大陆手机号码。")


# 验证密码格式
def validate_password(value: str):
    """密码格式验证：8-64位，必须包含字母和数字"""
    if not value or value.strip() == "":
        raise ValueError("密码不能为空")
    value = value.strip()
    if not re.match(r"^(?=.*[a-zA-Z])(?=.*\d).{8,64}$", value):
        raise ValueError("密码格式无效，必须包含字母和数字，长度为8到64个字符。")


# 验证身份证格式
def validate_identity_card(value: str):
    """中国大陆身份证验证"""
    error_msg = "身份证号格式无效"
    if not value:
        raise ValueError(error_msg)

    id_card = value.strip()
    if len(id_card) != 18:
        raise ValueError(error_msg)

    if not re.match(r"^[1-9]\d{16}[\dXx]$", id_card):
        raise ValueError(error_msg)

    if not re.match(r"^[1-9]\d{5}$", id_card[:6]):
        raise ValueError(error_msg)

    birth_date_str = id_card[6:14]
    try:
        birth_date = datetime.strptime(birth_date_str, "%Y%m%d")
        current_year = datetime.now().year
        if birth_date.year > current_year or (current_year - birth_date.year) > 120:
            raise ValueError(error_msg)
    except ValueError:
        raise ValueError(error_msg)

    check_code = id_card[-1].upper()
    coefficients = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
    check_code_map = {0: "1", 1: "0", 2: "X", 3: "9", 4: "8", 5: "7", 6: "6", 7: "5", 8: "4", 9: "3", 10: "2"}
    total = sum(int(id_card[i]) * coefficients[i] for i in range(17))
    remainder = total % 11
    expected_check_code = check_code_map[remainder]

    if check_code != expected_check_code:
        raise ValueError(error_msg)

    if not re.match(r"^\d{3}$", id_card[14:17]):
        raise ValueError(error_msg)


# 验证url格式
def validate_url(value: str) -> None:
    """URL格式验证"""
    if not value:
        return

    url_pattern = re.compile(
        r"^https?://"
        r"(?:(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+"
        r"[a-zA-Z]{2,}|"
        r"localhost|"
        r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"
        r"(?::\d{1,5})?"
        r"(?:/[^\s]*)?"
        r"$",
        re.IGNORECASE,
    )

    if not url_pattern.match(value):
        raise ValueError("URL格式无效，需以http/https开头")


# 验证验证码格式
def validate_verifycode(value: str):
    """验证码格式验证：6位数字"""
    if not re.match(r"^\d{6}$", value):
        raise ValueError("验证码格式无效，应为6位数字。")


# 租户编码格式
def validate_tenant_code(value: str):
    """
    租户编码（code）验证器
    规则：
    1. 非空
    2. 以小写字母开头
    3. 仅包含小写字母、数字、下划线、中划线
    4. 长度 1-64 字符
    """
    # 非空校验
    if not value or value.strip() == "":
        raise ValueError("租户编码（code）不能为空")

    # 格式+长度校验（正则已包含长度限制：[a-z] + 最多63个合法字符 = 总长度≤64）
    code_pattern = r"^[a-z][a-z0-9_\-]{0,63}$"
    if not re.match(code_pattern, value.strip()):
        raise ValueError("租户编码格式错误：必须以小写字母开头，仅包含小写字母、数字、下划线、中划线，长度1-64")


# 角色编码格式
def validate_role_code(value: str):
    """
    角色编码（code）验证器
    规则：
    1. 非空
    2. 以大写字母/下划线开头
    3. 仅包含大写字母、数字、下划线
    4. 长度 1-50 字符
    """
    # 补充非空校验（编码不能为空，符合通用业务逻辑）
    if not value or value.strip() == "":
        raise ValueError("角色编码（code）不能为空")

    # 格式+长度校验（正则已包含长度限制：[A-Z_] + 最多49个合法字符 = 总长度≤50）
    code_pattern = r"^[A-Z_][A-Z0-9_]{0,49}$"
    if not re.match(code_pattern, value.strip()):
        raise ValueError("角色编码格式错误：必须以大写字母/下划线开头，仅包含大写字母、数字、下划线，长度1-50")


# 权限码格式
def validate_permission_code(value: str):
    """
    权限代码格式验证：
    1. 结构：资源:操作[:范围]（必须包含至少 资源:操作 两部分）
    2. 字符：仅小写字母、数字、下划线、冒号，开头为小写字母/下划线
    3. 长度：1-100 字符
    """
    # 1. 长度校验
    if not (1 <= len(value) <= 100):
        raise ValueError(
            "权限编码格式错误：长度必须为1-100字符，且需符合「资源:操作[:范围]」结构（仅包含小写字母、数字、下划线、冒号，以小写字母/下划线开头）"
        )

    # 2. 格式正则校验（覆盖结构+字符规则）
    # 正则说明：
    # ^[a-z_]        开头：小写字母/下划线
    # [a-z0-9_]*     资源部分：小写字母/数字/下划线（可空？不，资源:操作 是必须的）
    # :              分隔符1
    # [a-z0-9_]+     操作部分：至少1个小写字母/数字/下划线
    # (:[a-z0-9_]+)? 可选的范围部分：冒号+至少1个小写字母/数字/下划线
    # $              结尾
    pattern = r"^[a-z_][a-z0-9_]*:[a-z0-9_]+(:[a-z0-9_]+)?$"
    if not re.match(pattern, value):
        raise ValueError(
            "权限编码格式错误：必须符合「资源:操作[:范围]」结构（仅包含小写字母、数字、下划线、冒号，以小写字母/下划线开头，长度1-100）"
        )


# === 新增验证器 ===


# 验证昵称格式（2-20个字符，支持中文、字母、数字、下划线）
def validate_nickname(value: str):
    """昵称格式验证：2-20个字符，支持中文、字母、数字、下划线"""
    if not re.match(r"^[\u4e00-\u9fa5A-Za-z0-9_]{2,20}$", value):
        raise ValueError("昵称格式无效，应为2到20个字符，支持中文、字母、数字、下划线")


# 验证真实姓名（2-10个汉字）
def validate_realname(value: str):
    """真实姓名验证：2-10个汉字"""
    if not re.match(r"^[\u4e00-\u9fa5]{2,10}$", value):
        raise ValueError("真实姓名格式无效，应为2到10个汉字")


# 验证年龄范围（0-150）
def validate_age(value: int):
    """年龄验证：0-150岁"""
    if not isinstance(value, int) or value < 0 or value > 150:
        raise ValueError("年龄无效，应为0到150之间的整数")


# 验证状态码（通常用于软删除等场景）
def validate_status(value: int):
    """状态验证：0=禁用/删除，1=正常/启用"""
    if value not in [0, 1]:
        raise ValueError("状态无效，应为0或1")


# 验证文件扩展名
def validate_file_extension(value: str, allowed_extensions: List[str] = None):
    """文件扩展名验证"""
    if allowed_extensions is None:
        allowed_extensions = [".jpg", ".jpeg", ".png", ".gif", ".pdf", ".doc", ".docx"]

    if not any(value.lower().endswith(ext) for ext in allowed_extensions):
        raise ValueError(f"文件格式无效，只支持{', '.join(allowed_extensions)}格式")


# 验证日期格式（YYYY-MM-DD）
def validate_date(value: str):
    """日期格式验证：YYYY-MM-DD"""
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        raise ValueError("日期格式无效，应为YYYY-MM-DD格式")

    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise ValueError("日期格式无效，请输入有效日期")


# 验证时间格式（HH:MM:SS）
def validate_time(value: str):
    """时间格式验证：HH:MM:SS"""
    if not re.match(r"^\d{2}:\d{2}:\d{2}$", value):
        raise ValueError("时间格式无效，应为HH:MM:SS格式")

    try:
        datetime.strptime(value, "%H:%M:%S")
    except ValueError:
        raise ValueError("时间格式无效，请输入有效时间")


# 验证日期时间格式（YYYY-MM-DD HH:MM:SS）
def validate_datetime(value: str):
    """日期时间格式验证：YYYY-MM-DD HH:MM:SS"""
    if not re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$", value):
        raise ValueError("日期时间格式无效，应为YYYY-MM-DD HH:MM:SS格式")

    try:
        datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        raise ValueError("日期时间格式无效，请输入有效日期时间")


# 验证IP地址格式
def validate_ip_address(value: str):
    """IP地址格式验证"""
    pattern = r"^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$"
    if not re.match(pattern, value):
        raise ValueError("IP地址格式无效")


# 验证端口号（1-65535）
def validate_port(value: int):
    """端口号验证：1-65535"""
    if not isinstance(value, int) or value < 1 or value > 65535:
        raise ValueError("端口号无效，应为1到65535之间的整数")


# 验证排序字段（通常用于列表排序）
def validate_order_field(value: str, allowed_fields: List[str] = None):
    """排序字段验证"""
    if allowed_fields and value not in allowed_fields:
        raise ValueError(f"排序字段无效，可选值为{', '.join(allowed_fields)}")


# 验证排序方向
def validate_order_direction(value: str):
    """排序方向验证：asc或desc"""
    if value not in ["asc", "desc"]:
        raise ValueError("排序方向无效，应为asc或desc")


# 验证分页参数
def validate_pagination(page: int, page_size: int, max_page_size: int = 100):
    """分页参数验证"""
    if page < 1:
        raise ValueError("页码无效，应大于等于1")

    if page_size < 1 or page_size > max_page_size:
        raise ValueError(f"每页数量无效，应为1到{max_page_size}之间的整数")


def validate_model_business_type(value: str):
    """
    业务类型格式验证：仅允许小写字母、下划线，长度3-32位
    """
    if not re.match(r"^[a-z_]{3,32}$", value):
        raise ValueError(f"业务类型格式无效，应为3-32位小写字母/下划线组合，当前值：{value}")

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
    if not re.match(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$", value):
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


# 验证权限码格式
def validate_permission_code(value: str):
    """权限代码格式验证：资源:操作[:范围]"""
    if not re.match(r"^[a-z][a-z0-9_:]*:[a-z][a-z0-9_]*(:[a-z][a-z0-9_]*)?$", value):
        raise ValueError("权限代码格式无效，必须为：资源:操作[:范围]")


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


# 验证性别（0=未知，1=男，2=女）
def validate_gender(value: int):
    """性别验证：0=未知，1=男，2=女"""
    if value not in [0, 1, 2]:
        raise ValueError("性别无效，应为0、1或2")


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

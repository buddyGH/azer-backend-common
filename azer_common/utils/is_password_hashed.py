# azer_common/utils/is_password_hashed.py
def is_password_hashed(password: str) -> bool:
    """检查密码是否已经哈希"""
    # 支持多种哈希格式的检测
    hash_prefixes = [
        "$argon2id$",  # Argon2id
        "$argon2d$",  # Argon2d
        "$argon2i$",  # Argon2i
        "$2b$",  # bcrypt
        "$2a$",
        "$2y$",
        "$pbkdf2-sha256$",  # PBKDF2
        "$scrypt$",  # scrypt
    ]

    return any(password.startswith(prefix) for prefix in hash_prefixes)

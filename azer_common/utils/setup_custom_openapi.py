# azer_common/utils/openapi_utils.py
from typing import List, Optional, Dict, Any
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi  # 直接使用FastAPI原生函数


def setup_custom_openapi(
        app: FastAPI,
        server_description: Optional[str] = None,
        extra_servers: Optional[List[Dict[str, Any]]] = None,
        openapi_title: Optional[str] = None,
        openapi_version: Optional[str] = None,
        tags: Optional[List[Dict[str, Any]]] = None,
        global_security: Optional[List[Dict[str, List[str]]]] = None,
        openapi_description: Optional[str] = None,
        contact: Optional[Dict[str, Any]] = None,
        license_info: Optional[Dict[str, Any]] = None
) -> None:
    """
    为 FastAPI 应用配置自定义 OpenAPI 规范（兼容原生get_openapi，不修改源码）
    核心解决：Swagger UI 调试时请求路径缺失 root_path 的问题
    扩展能力：支持接口分组标签、全局认证规则、多环境服务器配置等

    Args:
        app: FastAPI 应用实例
        server_description: 主服务器（root_path）的描述文本
        extra_servers: 额外的服务器配置（如测试/开发环境，格式同OpenAPI servers规范）
        openapi_title: 自定义OpenAPI标题（默认使用app.title）
        openapi_version: 自定义OpenAPI版本（默认使用app.version）
        tags: OpenAPI接口分组标签（格式：[{"name": "auth", "description": "认证接口"}]）
        global_security: 全局安全认证规则（格式：[{"BearerAuth": []}]，覆盖所有接口）
        openapi_description: OpenAPI文档整体描述
        contact: 联系人信息（格式：{"name": "运维组", "email": "ops@azer.cc"}）
        license_info: 许可证信息（格式：{"name": "MIT", "url": "https://mit-license.org/"}）
    """

    def custom_openapi() -> Dict[str, Any]:
        # 缓存已生成的schema，避免重复计算
        if app.openapi_schema:
            return app.openapi_schema

        # ========== 核心：处理root_path，生成servers配置 ==========
        # 归一化root_path：处理空值/多斜杠/无斜杠等边界情况
        root_path = app.root_path.strip("/")
        normalized_root_path = f"/{root_path}" if root_path else ""

        # 构建基础servers（包含root_path）
        servers = []
        if normalized_root_path:
            servers.append({
                "url": normalized_root_path,
                "description": server_description
            })
        # 合并额外的服务器配置（如测试/开发环境）
        if extra_servers and isinstance(extra_servers, list):
            servers.extend(extra_servers)

        # ========== 调用FastAPI原生get_openapi生成基础规范 ==========
        openapi_schema = get_openapi(
            title=openapi_title or app.title,
            version=openapi_version or app.version,
            routes=app.routes,
            servers=servers if servers else None,  # 传递root_path相关的servers
            tags=tags,
            description=openapi_description,
            contact=contact,
            license_info=license_info
        )

        # ========== 追加全局认证规则（不修改原生函数，仅后处理schema） ==========
        if global_security and isinstance(global_security, list):
            openapi_schema["security"] = global_security

        # 缓存生成的schema
        app.openapi_schema = openapi_schema
        return openapi_schema

    # 替换app默认的openapi生成逻辑
    app.openapi = custom_openapi

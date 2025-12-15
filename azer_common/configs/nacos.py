import json
import socket
from typing import Optional, List, Callable, Dict, Any
import yaml
from v2.nacos import (
    NacosConfigService,
    NacosNamingService,
    ClientConfigBuilder,
    GRPCConfig,
    ConfigParam,
    RegisterInstanceParam,
    DeregisterInstanceParam,
    BatchRegisterInstanceParam,
    GetServiceParam,
    ListServiceParam,
    ListInstanceParam,
    SubscribeServiceParam,
    Instance,
)


def get_host_ip() -> str:
    """获取本机真实IP（兼容多网卡）"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    finally:
        s.close()
    return ip


def load_config(content: str) -> dict:
    """兼容解析JSON/YAML配置"""
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return yaml.safe_load(content)


class NacosClientV3:
    """适配nacos-sdk-python v3的客户端封装

    注意：这是一个异步客户端，所有方法都需要在async环境中使用
    """

    def __init__(
        self,
        server_address: str,
        namespace_id: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        log_level: str = "INFO",
        grpc_timeout: int = 5000,
    ):
        """初始化Nacos客户端

        Args:
            server_address: Nacos服务端地址（如：127.0.0.1:8848）
            namespace_id: 命名空间ID
            username: 用户名（可选）
            password: 密码（可选）
            log_level: 日志级别（默认INFO）
            grpc_timeout: gRPC超时时间（毫秒，默认5000）
        """
        self.client_config = (
            ClientConfigBuilder()
            .server_address(server_address)
            .namespace_id(namespace_id)
            .username(username)
            .password(password)
            .log_level(log_level)
            .grpc_config(GRPCConfig(grpc_timeout=grpc_timeout))
            .build()
        )

        self.config_client: Optional[NacosConfigService] = None
        self.naming_client: Optional[NacosNamingService] = None

        self.service_ip = get_host_ip()
        self.service_name: Optional[str] = None
        self.service_port: Optional[int] = None
        self.service_group: Optional[str] = None

    async def init_clients(self):
        """异步初始化配置/命名客户端（必需在使用前调用）"""
        self.config_client = await NacosConfigService.create_config_service(self.client_config)
        self.naming_client = await NacosNamingService.create_naming_service(self.client_config)

    def set_service(
        self,
        service_name: str,
        service_port: int,
        service_group: str = "DEFAULT_GROUP",
        service_ip: Optional[str] = None,
    ):
        """设置服务注册信息

        Args:
            service_name: 服务名称
            service_port: 服务端口
            service_group: 服务分组（默认DEFAULT_GROUP）
            service_ip: 服务IP地址（默认自动获取）
        """
        self.service_name = service_name
        self.service_port = service_port
        self.service_group = service_group
        if service_ip:
            self.service_ip = service_ip

    async def register_service(
        self,
        weight: float = 1.0,
        cluster_name: str = "DEFAULT",
        metadata: Optional[Dict[str, Any]] = None,
        enabled: bool = True,
        healthy: bool = True,
        ephemeral: bool = True,
    ) -> bool:
        """注册服务实例

        Args:
            weight: 权重（默认1.0）
            cluster_name: 集群名称（默认DEFAULT）
            metadata: 元数据（默认{"env": "dev"}）
            enabled: 是否启用（默认True）
            healthy: 是否健康（默认True）
            ephemeral: 是否为临时实例（默认True）

        Returns:
            bool: 注册是否成功

        Raises:
            ValueError: 服务名/IP/端口未设置
        """
        if not all([self.service_name, self.service_ip, self.service_port]):
            raise ValueError("服务名/IP/端口未设置，请先调用set_service()")

        register_param = RegisterInstanceParam(
            service_name=self.service_name,
            group_name=self.service_group,
            ip=self.service_ip,
            port=self.service_port,
            weight=weight,
            cluster_name=cluster_name,
            metadata=metadata or {"env": "dev"},
            enabled=enabled,
            healthy=healthy,
            ephemeral=ephemeral,
        )

        return await self.naming_client.register_instance(register_param)

    async def update_service_instance(
        self,
        weight: float = 1.0,
        cluster_name: str = "DEFAULT",
        metadata: Optional[Dict[str, Any]] = None,
        enabled: bool = True,
        healthy: bool = True,
        ephemeral: bool = True,
    ) -> bool:
        """更新服务实例信息

        Args:
            weight: 权重（默认1.0）
            cluster_name: 集群名称（默认DEFAULT）
            metadata: 元数据（默认{"env": "dev"}）
            enabled: 是否启用（默认True）
            healthy: 是否健康（默认True）
            ephemeral: 是否为临时实例（默认True）

        Returns:
            bool: 更新是否成功
        """
        if not all([self.service_name, self.service_ip, self.service_port]):
            raise ValueError("服务名/IP/端口未设置，请先调用set_service()")

        register_param = RegisterInstanceParam(
            service_name=self.service_name,
            group_name=self.service_group,
            ip=self.service_ip,
            port=self.service_port,
            weight=weight,
            cluster_name=cluster_name,
            metadata=metadata or {"env": "dev"},
            enabled=enabled,
            healthy=healthy,
            ephemeral=ephemeral,
        )

        return await self.naming_client.update_instance(register_param)

    async def batch_register_services(
        self, instances: List[Dict[str, Any]], service_name: Optional[str] = None, group_name: Optional[str] = None
    ) -> bool:
        """批量注册服务实例

        Args:
            instances: 实例列表，每个实例包含ip, port等字段
            service_name: 服务名称（如未提供则使用set_service设置的名称）
            group_name: 服务分组（如未提供则使用set_service设置的分组）

        Returns:
            bool: 注册是否成功
        """
        if not self.naming_client:
            raise RuntimeError("命名客户端未初始化，请先调用init_clients()")

        service_name = service_name or self.service_name
        group_name = group_name or self.service_group

        if not service_name:
            raise ValueError("服务名未设置")

        # 构建BatchRegisterInstanceParam所需的实例列表
        instance_params = []
        for instance in instances:
            instance_params.append(
                RegisterInstanceParam(
                    service_name=service_name,
                    group_name=group_name,
                    ip=instance.get("ip"),
                    port=instance.get("port"),
                    weight=instance.get("weight", 1.0),
                    cluster_name=instance.get("cluster_name", "DEFAULT"),
                    metadata=instance.get("metadata", {}),
                    enabled=instance.get("enabled", True),
                    healthy=instance.get("healthy", True),
                    ephemeral=instance.get("ephemeral", True),
                )
            )

        batch_param = BatchRegisterInstanceParam(
            service_name=service_name, group_name=group_name, instances=instance_params
        )

        return await self.naming_client.batch_register_instances(batch_param)

    async def deregister_service(self) -> bool:
        """注销服务实例

        Returns:
            bool: 注销是否成功
        """
        if not all([self.service_name, self.service_ip, self.service_port]):
            return False

        deregister_param = DeregisterInstanceParam(
            service_name=self.service_name, group_name=self.service_group, ip=self.service_ip, port=self.service_port
        )

        return await self.naming_client.deregister_instance(deregister_param)

    async def get_config(self, data_id: str, group: str = "DEFAULT_GROUP", parse_json: bool = True) -> Any:
        """获取配置

        Args:
            data_id: 配置ID
            group: 配置分组（默认DEFAULT_GROUP）
            parse_json: 是否解析为JSON/YAML（默认True）

        Returns:
            配置内容（字符串或解析后的字典）

        Raises:
            RuntimeError: 配置客户端未初始化
            ValueError: 配置不存在
        """
        if not self.config_client:
            raise RuntimeError("配置客户端未初始化，请先调用init_clients()")

        config_param = ConfigParam(data_id=data_id, group=group)
        content = await self.config_client.get_config(config_param)

        if not content:
            raise ValueError(f"配置不存在：data_id={data_id}, group={group}")

        if parse_json:
            return load_config(content)
        return content

    async def add_config_listener(self, data_id: str, group: str, callback: Callable[[Dict[str, Any]], None]):
        """添加配置变更监听器

        Args:
            data_id: 配置ID
            group: 配置分组
            callback: 配置变更回调函数，接收配置字典参数
        """
        if not self.config_client:
            raise RuntimeError("配置客户端未初始化，请先调用init_clients()")

        async def config_callback(tenant: str, data_id: str, group: str, content: str):
            config = load_config(content)
            callback(config)

        await self.config_client.add_listener(data_id, group, config_callback)

    async def remove_config_listener(self, data_id: str, group: str, callback: Callable):
        """移除配置监听器

        Args:
            data_id: 配置ID
            group: 配置分组
            callback: 之前添加的回调函数
        """
        if not self.config_client:
            raise RuntimeError("配置客户端未初始化，请先调用init_clients()")

        await self.config_client.remove_listener(data_id, group, callback)

    async def subscribe_service(
        self,
        service_name: str,
        group: str,
        callback: Callable[[List[Dict[str, Any]]], None],
        clusters: Optional[List[str]] = None,
    ):
        """订阅服务实例变更

        Args:
            service_name: 服务名称
            group: 服务分组
            callback: 服务变更回调函数，接收实例列表参数
            clusters: 集群列表（可选）
        """
        if not self.naming_client:
            raise RuntimeError("命名客户端未初始化，请先调用init_clients()")

        async def service_callback(instance_list: List[Instance]):
            instances = [
                {
                    "ip": ins.ip,
                    "port": ins.port,
                    "weight": ins.weight,
                    "healthy": ins.healthy,
                    "enabled": ins.enabled,
                    "metadata": ins.metadata,
                }
                for ins in instance_list
            ]
            callback(instances)

        subscribe_param = SubscribeServiceParam(
            service_name=service_name, group_name=group, clusters=clusters or [], subscribe_callback=service_callback
        )
        await self.naming_client.subscribe(subscribe_param)

    async def unsubscribe_service(
        self,
        service_name: str,
        group: str,
        callback: Callable[[List[Dict[str, Any]]], None],
        clusters: Optional[List[str]] = None,
    ):
        """取消订阅服务实例变更

        Args:
            service_name: 服务名称
            group: 服务分组
            callback: 之前添加的回调函数
            clusters: 集群列表（可选）
        """
        if not self.naming_client:
            raise RuntimeError("命名客户端未初始化，请先调用init_clients()")

        subscribe_param = SubscribeServiceParam(
            service_name=service_name, group_name=group, clusters=clusters or [], subscribe_callback=callback
        )
        await self.naming_client.unsubscribe(subscribe_param)

    async def get_service_instances(
        self,
        service_name: str,
        group: str = "DEFAULT_GROUP",
        clusters: Optional[List[str]] = None,
        healthy_only: Optional[bool] = None,
        subscribe: bool = True,
    ) -> List[Dict[str, Any]]:
        """获取服务实例列表

        Args:
            service_name: 服务名称
            group: 服务分组
            clusters: 集群列表
            healthy_only: 是否只返回健康实例（None表示返回所有）
            subscribe: 是否订阅服务变更（默认True）

        Returns:
            服务实例列表
        """
        if not self.naming_client:
            raise RuntimeError("命名客户端未初始化，请先调用init_clients()")

        list_param = ListInstanceParam(
            service_name=service_name,
            group_name=group,
            clusters=clusters or [],
            healthy_only=healthy_only,
            subscribe=subscribe,
        )

        instances = await self.naming_client.list_instances(list_param)

        return [
            {
                "ip": ins.ip,
                "port": ins.port,
                "weight": ins.weight,
                "healthy": ins.healthy,
                "enabled": ins.enabled,
                "metadata": ins.metadata,
            }
            for ins in instances
        ]

    async def get_service_info(
        self, service_name: str, group: str = "DEFAULT_GROUP", clusters: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """获取服务信息（包含实例列表）

        Args:
            service_name: 服务名称
            group: 服务分组
            clusters: 集群列表

        Returns:
            服务信息字典
        """
        if not self.naming_client:
            raise RuntimeError("命名客户端未初始化，请先调用init_clients()")

        get_param = GetServiceParam(service_name=service_name, group_name=group, clusters=clusters or [])

        service = await self.naming_client.get_service(get_param)

        return {
            "name": service.name,
            "group_name": service.group_name,
            "clusters": service.clusters,
            "hosts": [
                {
                    "ip": host.ip,
                    "port": host.port,
                    "weight": host.weight,
                    "healthy": host.healthy,
                    "enabled": host.enabled,
                    "metadata": host.metadata,
                }
                for host in service.hosts
            ],
        }

    async def list_services(
        self,
        group_name: str = "DEFAULT_GROUP",
        namespace_id: Optional[str] = None,
        page_no: int = 1,
        page_size: int = 100,
    ) -> Dict[str, Any]:
        """获取服务列表

        Args:
            group_name: 服务分组
            namespace_id: 命名空间ID（默认使用初始化时设置的namespace）
            page_no: 页码
            page_size: 每页大小

        Returns:
            服务列表信息
        """
        if not self.naming_client:
            raise RuntimeError("命名客户端未初始化，请先调用init_clients()")

        list_param = ListServiceParam(
            group_name=group_name,
            namespace_id=namespace_id or self.client_config.namespace_id,
            page_no=page_no,
            page_size=page_size,
        )

        service_list = await self.naming_client.list_services(list_param)
        return {"count": service_list.count, "service_list": service_list.services}

    async def publish_config(
        self, data_id: str, content: str, group: str = "DEFAULT_GROUP", config_type: str = "yaml", **kwargs
    ) -> bool:
        """发布配置

        Args:
            data_id: 配置ID
            content: 配置内容
            group: 配置分组（默认DEFAULT_GROUP）
            config_type: 配置类型（json/yaml等）
            **kwargs: 其他配置参数，如tag, app_name等

        Returns:
            bool: 发布是否成功
        """
        if not self.config_client:
            raise RuntimeError("配置客户端未初始化，请先调用init_clients()")

        config_param = ConfigParam(data_id=data_id, group=group, content=content, type=config_type, **kwargs)

        return await self.config_client.publish_config(config_param)

    async def delete_config(self, data_id: str, group: str = "DEFAULT_GROUP") -> bool:
        """删除配置

        Args:
            data_id: 配置ID
            group: 配置分组（默认DEFAULT_GROUP）

        Returns:
            bool: 删除是否成功
        """
        if not self.config_client:
            raise RuntimeError("配置客户端未初始化，请先调用init_clients()")

        config_param = ConfigParam(data_id=data_id, group=group)
        return await self.config_client.remove_config(config_param)

    async def server_health(self) -> Dict[str, bool]:
        """检查服务器健康状态

        Returns:
            包含配置服务和命名服务健康状态的字典
        """
        health_status = {}

        if self.config_client:
            health_status["config_service"] = await self.config_client.server_health()

        if self.naming_client:
            health_status["naming_service"] = await self.naming_client.server_health()

        return health_status

    async def shutdown(self):
        """关闭客户端（释放资源）"""
        if self.config_client:
            await self.config_client.shutdown()
        if self.naming_client:
            await self.naming_client.shutdown()

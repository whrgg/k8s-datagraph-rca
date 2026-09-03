# 本地 Registry 配置说明

## 工作原理

1. **Registry 容器**：本地 Docker Registry 运行在 `localhost:5001`（容器内 5000），并代理 Docker Hub 请求。
2. **Kind 配置**：通过 `containerdConfigPatches` 让 Kind 集群从 `/etc/containerd/certs.d` 读取 registry 配置。
3. **节点配置**：各 Kind 节点在 `/etc/containerd/certs.d/docker.io/` 注入 `hosts.toml`。
4. **透明镜像缓存**：Pod 拉取镜像（如 `redis:latest`）时，节点 containerd 优先访问 `http://kind-registry:5000`。
   - **缓存未命中**：Registry 从 Docker Hub 拉取并缓存。
   - **缓存命中**：Registry 直接从本地磁盘返回。

## 步骤 1：启动 Registry 容器

使用脚本以 proxy 模式启动 Registry：

```bash
chmod +x registry/setup-registry.sh
./registry/setup-registry.sh
```

脚本会：
1. 在端口 `5001` 启动 `kind-registry` 容器
2. 挂载 `registry/registry-config.yml` 启用 Docker Hub 镜像代理
3. 将 Registry 连接到 `kind` 网络（若已存在）

## 步骤 2：创建 Kind 集群

集群创建脚本会自动配置节点使用本地 Registry 作为 Docker Hub 镜像源。

## 配置文件

- `registry/registry-config.yml`：Registry proxy 配置
- `registry/setup-registry.sh`：一键启动脚本

## 验证

```bash
docker ps | grep kind-registry
curl -s http://localhost:5001/v2/_catalog
```

若 Registry 正常运行，应能看到 v2 API 响应。

## 常见问题

- **端口冲突**：确保 5001 未被占用
- **Kind 网络不存在**：先创建 Kind 集群，或手动 `docker network connect kind kind-registry`
- **镜像仍从 Docker Hub 拉取**：检查节点 `/etc/containerd/certs.d/docker.io/hosts.toml` 是否注入成功

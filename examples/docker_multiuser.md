# RSS MCP Docker Multi-User Usage

## 容器中的多用户支持

RSS MCP 容器现在支持多用户配置，每个用户都有独立的配置目录。

### 🏗️ 构建容器

```bash
# 构建容器镜像
docker build -t rss-mcp .

# 或使用 podman
podman build -t rss-mcp .
```

### 🚀 运行示例

#### 1. 基础运行 (默认用户)
```bash
docker run -d -p 8080:8080 --name rss-mcp-server rss-mcp
```

访问：
```bash
# 根端点
curl http://localhost:8080/

# 健康检查
curl http://localhost:8080/mcp/health

# 默认用户信息
curl http://localhost:8080/mcp/user-info
# 返回: {"user_id": "default", "headers_provided": false}
```

#### 2. 多用户 HTTP 访问
```bash
# 容器运行后，通过不同的 header 访问
curl -H "X-User-ID: alice" http://localhost:8080/mcp/user-info
curl -H "x-user-id: bob" http://localhost:8080/mcp/user-info    # 大小写不敏感
curl -H "X-USER-ID: charlie" http://localhost:8080/mcp/tools
```

#### 3. SSE 连接
```bash
# Alice 用户的 feed 更新流
curl -H "X-User-ID: alice" \
     -H "Accept: text/event-stream" \
     http://localhost:8080/sse/feed-updates

# Bob 用户的工具调用通知
curl -H "x-user-id: bob" \
     -H "Accept: text/event-stream" \
     http://localhost:8080/sse/tool-calls
```

#### 4. 持久化配置和缓存
```bash
# 挂载卷以持久化数据
docker run -d \
  -p 8080:8080 \
  -v ./config:/app/config \
  -v ./cache:/app/cache \
  --name rss-mcp-server \
  rss-mcp
```

挂载后的目录结构（运行时创建）：
```
./config/
├── default/
│   └── config.json       # 默认用户配置（首次访问时创建）
├── alice/
│   └── config.json       # Alice 用户配置（首次访问时创建）
└── bob/
    └── config.json       # Bob 用户配置（首次访问时创建）

./cache/
├── feeds/                # 用户特定数据  
├── sources/
├── entries/
└── abc123def.../         # URL hash 缓存（所有用户共享）
    └── content.json
```

#### 5. 环境变量控制
```bash
# 在容器中设置默认用户 ID (影响 stdio 模式)
docker run -d \
  -p 8080:8080 \
  -e RSS_MCP_USER=container-user \
  --name rss-mcp-server \
  rss-mcp

# 注意：HTTP 模式仍然优先使用 X-User-ID header
```

#### 6. 自定义配置
```bash
# 挂载自定义配置文件
docker run -d \
  -p 8080:8080 \
  -v ./custom-config.json:/app/config/myuser/config.json \
  --name rss-mcp-server \
  rss-mcp

# 然后通过 header 访问该用户
curl -H "X-User-ID: myuser" http://localhost:8080/mcp/user-info
```

### 🔧 开发和调试

#### 交互式运行
```bash
# 交互式运行以进行调试
docker run -it --rm \
  -p 8080:8080 \
  -v ./config:/app/config \
  -v ./cache:/app/cache \
  rss-mcp /bin/bash

# 在容器内手动启动服务器
rss-mcp serve http --host 0.0.0.0 --port 8080
```

#### 查看日志
```bash
# 查看容器日志
docker logs rss-mcp-server

# 实时跟踪日志
docker logs -f rss-mcp-server
```

#### 健康检查
```bash
# 检查容器健康状态
docker ps
# HEALTHY 状态表示服务运行正常

# 手动健康检查
docker exec rss-mcp-server curl -f http://localhost:8080/mcp/health
```

### 🌐 Kubernetes 部署

```yaml
# rss-mcp-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: rss-mcp
spec:
  replicas: 1
  selector:
    matchLabels:
      app: rss-mcp
  template:
    metadata:
      labels:
        app: rss-mcp
    spec:
      containers:
      - name: rss-mcp
        image: rss-mcp:latest
        ports:
        - containerPort: 8080
        env:
        - name: RSS_MCP_CACHE
          value: "/app/cache"
        volumeMounts:
        - name: config-volume
          mountPath: /app/config
        - name: cache-volume
          mountPath: /app/cache
        livenessProbe:
          httpGet:
            path: /mcp/health
            port: 8080
          initialDelaySeconds: 10
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /mcp/health
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 10
      volumes:
      - name: config-volume
        persistentVolumeClaim:
          claimName: rss-mcp-config-pvc
      - name: cache-volume
        persistentVolumeClaim:
          claimName: rss-mcp-cache-pvc

---
apiVersion: v1
kind: Service
metadata:
  name: rss-mcp-service
spec:
  selector:
    app: rss-mcp
  ports:
  - protocol: TCP
    port: 8080
    targetPort: 8080
  type: LoadBalancer
```

### 🎯 多用户最佳实践

1. **HTTP 模式**: 始终通过 `X-User-ID` header 指定用户
2. **大小写**: Header 大小写不敏感，`X-User-ID`, `x-user-id`, `X-USER-ID` 都可以
3. **持久化**: 挂载 `/app/config` 和 `/app/cache` 目录
4. **安全**: 每个用户有独立配置，但缓存是共享的（节省资源）
5. **监控**: 使用 `/mcp/health` 端点进行健康检查

### 🐛 常见问题

**Q: 为什么我的用户配置没有生效？**
A: 确保 HTTP 请求中包含正确的 `X-User-ID` header。

**Q: 如何查看当前使用的用户？**
A: 访问 `/mcp/user-info` 端点查看当前识别的用户ID。

**Q: 容器重启后配置丢失？**
A: 请挂载 `/app/config` 目录以持久化用户配置。

**Q: SSE 连接断开？**
A: SSE 连接需要长连接支持，确保负载均衡器配置正确。
# Cloudreve-V4-AfdianPay

Cloudreve v4 Pro 自定义支付网关 — 爱发电支付渠道

## 这是什么？

在 Cloudreve 网盘和爱发电之间架一座桥：用户在 Cloudreve 购买套餐时，自动跳转到爱发电完成支付，支付完成后自动回调通知 Cloudreve 开通权益。

```
用户点击购买 → Cloudreve → AfdPay 生成爱发电付款链接 → 用户扫码支付
                                                          ↓
Cloudreve 开通权益 ← AfdPay 回调通知 ← 爱发电 Webhook 通知
```

## 前置准备

- Python 3.12+
- 一个爱发电账号
- 一个运行中的 Cloudreve v4 Pro

### 第一步：获取爱发电密钥

1. 注册/登录 [爱发电](https://afdian.com/)
2. 进入 [开发人员页面](https://afdian.com/dashboard/dev)
3. 复制页面上的 **user_id**
4. 复制页面底部的 **API Token**

### 第二步：获取 Cloudreve 通信密钥

1. 登录 Cloudreve 管理后台
2. 进入 **参数设置 → 增值服务 → 自定义付款渠道**
3. 设置一个 **通信密钥**（随便填一串字符串，但两边要一致）

---

## 安装

### 方式一：本地运行

```powershell
# 克隆项目
git clone https://github.com/yukaidi1220/Cloudreve-V4-AfdianPay.git afd-pay
cd afd-pay

# 安装依赖
pip install -e .

# 复制配置模板
copy .env.example .env
```

编辑 `.env`，填入你的实际值：

```env
SITE_URL=https://你的cloudreve域名.com
COMMUNICATION_KEY=你设置的通信密钥
AFDIAN_USER_ID=你的爱发电user_id
AFDIAN_TOKEN=你的爱发电API Token
PORT=5000
```

启动：

```powershell
python -m afd_pay.main
```

看到 `server_started` 日志说明启动成功。

### 方式二：Docker 部署

```bash
# 修改 docker-compose.yml 中的环境变量
vim docker-compose.yml

# 启动
docker-compose up -d

# 查看日志
docker-compose logs -f
```

### 方式三：下载二进制

直接从 [Releases](https://github.com/yukaidi1220/Cloudreve-V4-AfdianPay/releases) 下载编译好的二进制文件，解压后配置 `.env` 即可运行。

**适用系统：**

| 文件名 | 适用系统 | 最低要求 |
|--------|----------|----------|
| `afd-pay-windows-amd64.exe` | Windows 64位 | Windows 10+ |
| `afd-pay-windows-386.exe` | Windows 32位 | Windows 10+ |
| `afd-pay-linux-amd64` | Linux 64位 (x86_64) | GLIBC 2.17+ |
| `afd-pay-linux-386` | Linux 32位 (i386) | GLIBC 2.17+ |

---

## 配置 Cloudreve

1. 登录 Cloudreve 管理后台
2. 进入 **参数设置 → 增值服务 → 自定义付款渠道**
3. 填写：
   - **付款方式名称**：爱发电（随便写）
   - **支付接口地址**：`http://你的服务器IP或域名:5000/order`
   - **通信密钥**：与 `.env` 中 `COMMUNICATION_KEY` 完全一致

## 配置爱发电 Webhook

1. 进入 [爱发电开发人员页面](https://afdian.com/dashboard/dev)
2. 设置 **Webhook URL**：`http://你的服务器IP或域名:5000/afdian`
3. 点击保存，如果没有报错说明配置成功

---

## 所有配置项

在 `.env` 中配置，以下是完整列表：

| 变量名 | 必填 | 默认值 | 说明 |
|--------|:---:|--------|------|
| `SITE_URL` | ✅ | | Cloudreve 站点地址，不带末尾 `/` |
| `COMMUNICATION_KEY` | ✅ | | 与 Cloudreve 后台设置的通信密钥一致 |
| `AFDIAN_USER_ID` | ✅ | | 爱发电开发者页面获取 |
| `AFDIAN_TOKEN` | ✅ | | 爱发电开发者页面底部获取 |
| `PORT` | | `5000` | 监听端口 |
| `LOG_LEVEL` | | `INFO` | 日志级别：`DEBUG` / `INFO` / `WARNING` |
| `USER_AGENT_CLOUDREVE` | | `AfdPay` | 通知 Cloudreve 时的 User-Agent |
| `USER_AGENT_AFDIAN` | | `AfdPay` | 调用爱发电 API 时的 User-Agent |
| `DB_PATH` | | `data/afdian_pay.db` | SQLite 数据库文件路径 |
| `AFDIAN_API_BASE` | | `https://ifdian.net` | 爱发电 API 主域名（国内优先） |
| `AFDIAN_API_FALLBACK` | | `https://afdian.com` | 爱发电 API 回退域名 |
| `AFDIAN_PAYMENT_BASE` | | `https://ifdian.net` | 爱发电付款页面域名 |
| `MIN_AMOUNT_FEN` | | `500` | 最低订单金额，单位分（500=5元） |
| `NOTIFY_MAX_ATTEMPTS` | | `20` | 回调 Cloudreve 最大重试次数 |
| `NOTIFY_BASE_DELAY` | | `5.0` | 回调首次重试延迟（秒） |
| `NOTIFY_MAX_DELAY` | | `1800.0` | 回调最大重试间隔（秒，默认30分钟） |

---

## 支付流程详解

### 流程 1：创建订单

用户在 Cloudreve 点击购买套餐时触发：

1. Cloudreve 向 `POST /order` 发送订单请求（含金额、订单号、回调地址）
2. AfdPay 验证 Cloudreve 的 HMAC-SHA256 签名
3. 订单存入本地 SQLite 数据库
4. 生成爱发电付款链接返回给 Cloudreve
5. Cloudreve 将链接展示为二维码给用户扫码

### 流程 2：支付回调

用户在爱发电完成支付后触发：

1. 爱发电向 `POST /afdian` 发送 Webhook 通知
2. AfdPay 调用爱发电 API **二次确认**订单真实性（防止伪造）
3. 校验金额匹配
4. 原子标记订单为已支付
5. 异步 GET 通知 Cloudreve 的回调地址

### 流程 3：状态轮询

Cloudreve 可能主动查询订单状态：

1. Cloudreve 向 `GET /order?order_no=XXX&sign=XXX` 查询
2. AfdPay 验证签名，查询数据库返回 `PAID` 或 `UNPAID`

### 回调重试机制

通知 Cloudreve 时如果失败（网络超时、Cloudreve 暂时不可用等），自动指数退避重试：

```
5s → 10s → 20s → 40s → 80s → 160s → 300s → ... → 最大 1800s（30分钟）
```

最多重试 20 次，之后放弃并记录日志。

---

## API 端点

| 方法 | 路径 | 说明 | 调用方 |
|------|------|------|--------|
| `GET` | `/health` | 健康检查 | 运维监控 |
| `POST` | `/order` | 创建订单，返回付款链接 | Cloudreve |
| `GET` | `/order` | 查询订单状态 | Cloudreve |
| `POST` | `/afdian` | 支付回调通知 | 爱发电 |

### 健康检查响应

```json
GET /health

{
    "status": "ok",
    "version": "1.0.0",
    "db": "connected"
}
```

### 创建订单响应

成功：
```json
{"code": 0, "data": "https://afdian.com/order/create?user_id=xxx&remark=xxx&custom_price=50.00"}
```

失败：
```json
{"code": 500, "error": "签名已过期"}
```

### 查询订单状态响应

```json
{"code": 0, "data": "PAID"}
```

---

## 安全机制

### 签名验证

- **Cloudreve 请求**：HMAC-SHA256 + base64url 签名验证，防伪造请求
- **爱发电 Webhook**：收到后调用爱发电 API 二次确认订单真实性，防止伪造支付成功

### 其他安全措施

- `notify_url` 与 `site_url` 同域校验，防止 SSRF
- 请求体大小限制 1MB，防止 DoS
- 安全响应头（X-Content-Type-Options、X-Frame-Options、CSP）
- 常量时间签名比较（hmac.compare_digest），防时序攻击
- 已支付订单原子 CAS 更新，防并发竞态
- 错误信息脱敏，不泄露内部结构
- 环境变量空值/空格校验，启动时快速失败

---

## 项目结构

```
afd-pay/
├── pyproject.toml              # 项目配置、依赖声明
├── Dockerfile                  # Docker 多阶段构建
├── docker-compose.yml          # 一键部署
├── .env.example                # 配置模板
├── .gitignore
└── src/afd_pay/
    ├── __init__.py
    ├── config.py               # 配置管理（pydantic-settings）
    ├── database.py             # SQLite 数据库（aiosqlite）
    ├── main.py                 # Quart 应用工厂 + 生命周期
    ├── schemas.py              # Pydantic 请求/响应模型
    ├── routes/
    │   ├── health.py           # GET /health
    │   ├── order.py            # POST/GET /order
    │   └── webhook.py          # POST /afdian
    └── services/
        ├── afdian.py           # 爱发电 API 客户端
        ├── cloudreve.py        # Cloudreve 签名验证
        └── notifier.py         # 回调重试 Worker
```

---

## 常见问题

### 启动报错 "缺少必填配置项"

检查 `.env` 文件，确保 `SITE_URL`、`COMMUNICATION_KEY`、`AFDIAN_USER_ID`、`AFDIAN_TOKEN` 四项都已填写（不能是空字符串或纯空格）。

### 端口被占用

```
错误：端口 5000 已被占用
```

修改 `.env` 中的 `PORT` 为其他端口，或停掉占用该端口的程序。

### 用户支付后 Cloudreve 没有开通权益

1. 检查 AfdPay 日志，搜索 `notify_success` 或 `notify_failed`
2. 确认 `SITE_URL` 与 Cloudreve 实际地址一致（不带末尾 `/`）
3. 确认 `COMMUNICATION_KEY` 与 Cloudreve 后台设置完全一致
4. 确认 AfdPay 服务器能访问到 Cloudreve（网络可达）
5. 回调会自动重试（5s→10s→20s...最多 20 次），稍等片刻再看

### 爱发电回调没收到

1. 确认爱发电 Webhook URL 配置正确（格式：`http://域名:端口/afdian`）
2. 确认服务器防火墙/安全组放开了 `PORT` 端口
3. 检查 AfdPay 日志中是否有 `webhook_received` 记录
4. 如果完全没有日志，说明请求没到达 AfdPay，检查网络和端口

### 通信密钥怎么填？

在 `.env` 里的 `COMMUNICATION_KEY` 和 Cloudreve 后台自定义付款渠道里的 **通信密钥** 必须填一样的值。这是两边互相验证身份用的，随便填一串字符串就行，比如 `mySecretKey123`。

### 支付链接打不开

1. 检查爱发电 API 是否可达（`ifdian.net` 或 `afdian.com`）
2. 检查日志中是否有 `query_order_failed` 记录
3. 确认 `AFDIAN_USER_ID` 和 `AFDIAN_TOKEN` 正确

### 如何查看日志？

本地运行时日志直接输出到控制台。Docker 部署用 `docker-compose logs -f` 查看。

日志是 JSON 格式（`LOG_LEVEL=INFO` 时），每条日志包含事件名和关键字段：

```json
{"event": "order_created", "order_no": "20260528123456", "amount": 5000}
{"event": "order_marked_paid", "order_no": "20260528123456"}
{"event": "notify_success", "order_no": "20260528123456"}
```

设置 `LOG_LEVEL=DEBUG` 可看到更详细的日志（开发调试用）。

### 数据库在哪里？

默认在项目目录下的 `data/afdian_pay.db`，SQLite 单文件数据库。可通过 `DB_PATH` 配置修改路径。Docker 部署时通过 volume 持久化到宿主机。

### 支持多币种吗？

不支持。仅支持 CNY（人民币），非 CNY 的订单会被拒绝。Cloudreve 侧建议将默认货币设为 CNY。

### 能部署多个实例吗？

不建议。SQLite 是单文件数据库，多实例共享同一文件会导致数据损坏。如果需要高可用，建议用单实例 + 反向代理 + 进程守护（如 systemd、Docker restart policy）。

### 如何更新？

```powershell
cd afd-pay
git pull
pip install -e .
# 重启服务
```

Docker 部署：
```bash
docker-compose down
docker-compose build
docker-compose up -d
```

---

## 技术栈

- Python 3.12 + [Quart](https://quart.palletsprojects.com/)（异步 Web 框架）
- [aiosqlite](https://aiosqlite.omnilib.dev/)（SQLite 异步驱动）
- [httpx](https://www.python-httpx.org/)（异步 HTTP 客户端）
- [Pydantic](https://docs.pydantic.dev/)（数据验证）
- [Hypercorn](https://hypercorn.readthedocs.io/)（ASGI 服务器）
- [structlog](https://www.structlog.org/)（结构化日志）

## License

MIT

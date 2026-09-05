# 千岸 QianAn — 腾讯云函数 SCF 部署指南

## 前置条件

- 腾讯云账号（有云函数免费额度）
- 百炼平台 API Key（黑客松发放）
- 本地已安装 Python 3.10+

## 快速部署（5 步）

### 第 1 步：打包

```bash
cd qianan/server

# 创建部署目录
rm -rf deploy_pkg
mkdir -p deploy_pkg

# 安装依赖到 deploy_pkg
pip install -r scf_requirements.txt -t ./deploy_pkg/

# 拷贝应用代码
cp -r app scf_adapter.py scf_entry.py deploy_pkg/
cp -r data deploy_pkg/          # 运行时数据目录（已安装技能文件等）
cp -r rules deploy_pkg/         # 5 平台规则库（运行时必需；改过规则先 make sync-rules）
cp .env.example deploy_pkg/.env  # 部署时在控制台改环境变量

# 压缩
cd deploy_pkg
zip -r ../deploy.zip .
cd ..
```

### 第 2 步：创建云函数

1. 打开 [腾讯云函数控制台](https://console.cloud.tencent.com/scf)
2. 点击「新建」→「自定义创建」
3. 填写：
   - 函数名称：`qianan-api`
   - 运行环境：**Python 3.10**
   - 代码上传方式：**本地 zip 上传**
   - 上传文件：`deploy.zip`
   - 函数入口：`scf_entry.main_handler`
4. 内存：**512 MB**
5. 超时：**120 秒**

### 第 3 步：配置环境变量

在「函数配置」→「环境变量」中添加：

| 变量名 | 值 | 说明 |
|--------|-----|------|
| `BAILIAN_API_KEY` | 你的百炼 key | 黑客松发放 |
| `QIANAN_MOCK` | `1` | 无 key 时自动 mock；实测通过后改为 `0` |
| `BAILIAN_BASE_URL` | 百炼网关地址 | 见 `.env.example` |
| `BAILIAN_BASE_URL` | 你的网关地址 | 如 `https://apimart.ai/v1` |

### 第 4 步：配置 HTTP 触发器

1. 在「触发器管理」→「新建触发器」
2. 触发方式：**API 网关触发器**
3. 请求方法：**ANY**（或选 POST/GET）
4. 发布路径：`/api/*`
5. 发布环境：**发布到线上环境**

> 触发后会得到一个类似 `https://service-xxx-xxx.a.run.app` 的 URL

### 第 5 步：测试

```bash
# 健康检查
curl https://<你的函数URL>/api/health

# 生成测试
curl -X POST https://<你的函数URL>/api/generate \
  -H "Content-Type: application/json" \
  -d '{"product_name":"便携榨汁杯","selling_points":"USB-C快充，10秒出汁","platforms":["amazon"]}'
```

## 前端部署

前端部署到 **Vercel**（免费）：

```bash
cd qianan/web

# 设置环境变量
vercel env add NEXT_PUBLIC_API_URL production
# 输入你的云函数 URL，如：https://qianan-api-xxx.a.run.app

# 部署
vercel --prod
```

## 前端也部署到云托管（可选）

如果你希望全部用腾讯云，前端可以部署到 **云托管 CloudBase**：

```bash
cd qianan/web
npm run build

# 将 .next/standalone/ + .next/static/ + public/ 上传到 CloudBase 静态托管
```

## 成本估算

| 资源 | 免费额度 | 预估用量 | 费用 |
|------|---------|---------|------|
| 云函数 | 100 万次/月 | 评审试用 < 1000 次 | **0 元** |
| API 网关 | 100 万次/月 | < 1000 次 | **0 元** |
| 百炼算力 | 25000 Credits | 评审试用 < 1000 次 | **0 元**（比赛发放） |
| Vercel 前端 | 100GB 带宽/月 | < 1GB | **0 元** |

**结论：参赛阶段完全免费。**

## 常见问题

### Q: 函数调用超时？
A: 在 SCF 控制台 → 函数配置 → 超时时间改为 120s。

### Q: 看到 "ASGI server 冷启动超时"？
A: 正常。首次调用需 ~1.5s 拉起 uvicorn， Subsequent 调用复用。SCF 重试会处理超时。

### Q: 后端重启后任务结果丢失？
A: 当前 task_store 是内存的。正式版需要接入云开发数据库或 COS 做持久化。

### Q: 文件（图片/导出包）存在哪？
A: 当前存在函数实例的 /tmp（生命周期内有效）。正式版改用 COS 对象存储。

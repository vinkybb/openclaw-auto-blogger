# 博客自动生成流水线

基于 **OpenClaw** 的自动化博客内容生成系统：从 RSS 抓取文章，经 AI 摘要与扩写，输出 Markdown，并可发布到本地路径、GitHub、WordPress 等。

## 功能特性

- **RSS 内容抓取**：从多个订阅源自动获取最新文章
- **智能摘要**：使用 OpenClaw 生成内容摘要
- **深度扩写**：将摘要扩展为可读的完整博文
- **自动发布**：支持本地目录、GitHub、WordPress 等多平台（可配置）
- **灵活配置**：YAML 配置文件，按需定制来源与发布方式

## 目录结构

```
├── app.py                    # 主要入口
├── config.yaml               # 本地配置
├── config.yaml.example
├── requirements.txt
├── modules/
│   ├── gateway_invoke.py
│   ├── openclaw_client.py
│   ├── rss_fetcher.py
│   ├── summarizer.py
│   ├── expander.py
│   └── publisher.py
└── tests/
    ├── test_openclaw.py
    └── test_gateway_invoke.py
```

## 工作流程

```
RSS 源 → 抓取 → OpenClaw 摘要 → OpenClaw 扩写 → Markdown → 保存 / 远程发布
```

## 快速开始

### 1. 安装依赖

```bash
cd openclaw-auto-blogger
pip install -r requirements.txt
```

### 2. 配置

```bash
cp config.yaml.example config.yaml
# 编辑 config.yaml：rss.sources、openclaw、publish 等
```

### 3. OpenClaw Gateway

流水线通过 **HTTP** 调用 Gateway，需：

- Gateway 已启动并监听（示例端口 **18789**，与配置中 `gateway_url` / `base_url` 一致）
- 环境变量 **`OPENCLAW_GATEWAY_TOKEN`**（或配置 `openclaw.gateway_token`，不推荐写入仓库）

  **关于 Gateway token：** 完成 `openclaw onboard` 后，Gateway 侧通常会已有认证（向导会生成 `gateway.auth.token`，见 [Configuration Reference · Gateway](https://docs.openclaw.ai/gateway/configuration-reference#gateway-field-details)）。本仓库的 `OPENCLAW_GATEWAY_TOKEN` 或 `openclaw.gateway_token` 应填该值，需自行设置或写入本地 `config.yaml`。可在本机 `~/.openclaw/openclaw.json` 的 `gateway.auth` 中核对；勿将真实 token 提交到仓库。

- 在 Gateway 中允许经 HTTP 调用 `sessions_spawn`

  OpenClaw 对 `POST /tools/invoke` 额外维护一份 **HTTP 默认 deny 列表**。要在本机放行，在 **`~/.openclaw/openclaw.json`** 的 `gateway.tools` 里把该工具从默认拦截中移除，例如：

  ```json5
  {
    gateway: {
      tools: {
        allow: ["sessions_spawn"],
      },
    },
  }
  ```

  合并进已有 `gateway` 配置即可；修改后需 **重启 Gateway**。字段说明见 [Configuration Reference · gateway.tools](https://docs.openclaw.ai/gateway/configuration-reference#gateway-field-details)。

### 4. 运行流水线

```bash
# 处理所有抓取到的文章（按 RSS 配置）
python app.py

# 只处理前 5 篇
python app.py -n 5

# 仅抓取，不摘要/扩写
python app.py --fetch-only

# 试运行：不保存、不发布
python app.py --dry-run

python app.py -c /path/to/config.yaml
```

### 5. 测试

```bash
python tests/test_openclaw.py
```

未设置 `OPENCLAW_GATEWAY_TOKEN` 时，`test_openclaw.py` 可能跳过或失败于连接，属预期。

## 配置说明

| 段 | 说明 |
|----|------|
| `rss` | `sources`：名称、url、enabled |
| `openclaw` | `gateway_url` / `base_url`、`timeout`、`model`（可选）、`gateway_token`（可选，优先用环境变量） |
| `content` | 摘要长度、目标字数、语言、文风 `style`、是否 `include_source` |
| `publish` | `local`、`github`、`wordpress`、`webhook` 等开关与凭证 |

定时运行请使用系统 **cron** 或 **systemd timer** 调用 `python app.py`，本项目不包含内置调度器。

## OpenClaw 集成要点

客户端使用 `POST /tools/invoke` 调用 `sessions_spawn`。摘要与扩写在 [summarizer.py](modules/summarizer.py)、[expander.py](modules/expander.py) 中通过 `OpenClawClient.spawn_agent` 下发任务。

示例（需有效 token 与可达 Gateway）：

```python
from modules.openclaw_client import OpenClawClient

client = OpenClawClient({
    "gateway_url": "http://127.0.0.1:18789",
    "timeout": 300,
})
# 环境变量需已设置 OPENCLAW_GATEWAY_TOKEN
raw = client.spawn_agent("请用一句话说明 RSS 抓取的作用。", timeout_seconds=60)
```

## 注意事项

1. **版权与合规**：注意原文与生成内容的使用许可与站点条款。
2. **人工审核**：生成内容建议发布前人工检查。
3. **故障排查**：连接失败时检查 Gateway 地址、token、`sessions_spawn` 是否在 HTTP 层被放行。若显示子回话超时，可尝试增大 `config.yaml` 里 `openclaw.timeout`。

## License

[MIT](LICENSE)

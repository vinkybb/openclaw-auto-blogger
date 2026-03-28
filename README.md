# 博客自动生成流水线

基于 OpenClaw 框架构建的自动化博客内容生成系统。

## 功能特性

- **RSS 内容抓取**: 从多个 RSS 源自动获取最新内容
- **智能摘要**: 使用 OpenClaw AI 生成内容摘要
- **深度扩写**: 将摘要扩展为完整的博客文章
- **自动发布**: 支持多平台发布 (本地/Hugo/WordPress/GitHub Pages)
- **灵活配置**: YAML 配置文件，易于定制

## 架构说明

```
blog-pipeline/
├── app.py                    # 主程序入口
├── config.yaml               # 配置文件
├── config.yaml.example       # 配置示例
├── requirements.txt          # Python 依赖
└── modules/
    ├── __init__.py           # 模块导出
    ├── openclaw_client.py    # OpenClaw API 客户端
    ├── rss_fetcher.py        # RSS 抓取模块
    ├── summarizer.py         # 摘要生成模块
    ├── expander.py           # 文章扩写模块
    ├── image_gen.py          # 配图生成模块
    └── publisher.py          # 发布模块
```

## 工作流程

```
RSS 源 → 抓取文章 → 生成摘要 → 扩写文章 → 格式化 → 发布
           ↓           ↓           ↓
        原始内容    OpenClaw    OpenClaw
```

## 快速开始

### 1. 安装依赖

```bash
cd /root/home/blog-pipeline
pip install -r requirements.txt
```

### 2. 配置

```bash
cp config.yaml.example config.yaml
# 编辑 config.yaml，配置 RSS 源和 OpenClaw
```

### 3. 确保 OpenClaw 运行

```bash
# 检查状态
openclaw gateway status

# 如果未运行，启动它
openclaw gateway start
```

### 4. 运行测试

```bash
python tests/test_openclaw.py
```

### 5. 执行流水线

```bash
# 处理所有文章
python app.py

# 只处理 5 篇
python app.py -n 5

# 仅抓取文章
python app.py --fetch-only

# 指定配置文件
python app.py -c /path/to/config.yaml
```

## OpenClaw 集成说明

本项目使用 OpenClaw 的 **subagent** 能力进行 AI 任务处理：

### API 调用方式

```python
from modules.openclaw_client import OpenClawClient

client = OpenClawClient({'base_url': 'http://localhost:3000'})

# 生成摘要
summary = client.summarize(content, style="简洁")

# 扩写文章
article = client.expand(title, summary, word_count=1500)

# 生成标签
tags = client.generate_tags(content)
```

### 配置选项

```yaml
openclaw:
  base_url: "http://localhost:3000"  # OpenClaw Gateway 地址
  timeout: 300                        # 请求超时 (秒)
  model: null                         # 指定模型 (可选)
```

## 模块说明

### rss_fetcher.py - RSS 抓取

从配置的 RSS 源获取最新文章。

```python
from modules.rss_fetcher import RSSFetcher

fetcher = RSSFetcher(config)
articles = fetcher.fetch_all()
```

### summarizer.py - 摘要生成

使用 OpenClaw 生成文章摘要。

```python
from modules.summarizer import RSSSummarizer

summarizer = RSSSummarizer(config)
result = summarizer.summarize(title, content, style="简洁")
```

### expander.py - 文章扩写

将摘要扩写为完整文章。

```python
from modules.expander import ArticleExpander

expander = ArticleExpander(config)
article = expander.expand(title, summary, source_url=url)
```

### publisher.py - 内容发布

支持多种发布方式。

```python
from modules.publisher import Publisher

publisher = Publisher(config)
publisher.publish(article, platform='local')
```

## 自定义扩展

### 添加新的 RSS 源

编辑 `config.yaml`:

```yaml
rss:
  sources:
    - name: "我的博客"
      url: "https://example.com/feed.xml"
      enabled: true
```

### 自定义写作风格

```yaml
content:
  style: "技术深度分析"  # 或 "轻松有趣", "学术严谨" 等
  article_length: 2000   # 目标字数
```

### 添加新的发布平台

在 `modules/publisher.py` 中添加新的发布方法。

## 注意事项

1. **OpenClaw 依赖**: 确保 OpenClaw Gateway 正在运行
2. **网络连接**: RSS 抓取需要网络访问
3. **内容版权**: 注意原内容的使用许可
4. **生成质量**: AI 生成内容需要人工审核

## 故障排除

### OpenClaw 连接失败

```bash
# 检查 Gateway 状态
openclaw gateway status

# 查看日志
openclaw gateway logs

# 重启服务
openclaw gateway restart
```

### RSS 抓取失败

- 检查网络连接
- 验证 RSS URL 可访问
- 查看错误日志

### 内容生成质量不佳

- 调整 `content.style` 配置
- 增加 `content.article_length`
- 尝试不同的模型设置

## License

MIT
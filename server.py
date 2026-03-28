#!/usr/bin/env python3
"""博客流水线服务端 - 流式架构 + 取消/继续机制"""

import os
import sys
import json
import yaml
import subprocess
import threading
import queue
import time
import signal
from pathlib import Path
from datetime import datetime
from flask import Flask, Response, render_template, jsonify, request, stream_with_context
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

app = Flask(__name__)

# ============ 全局状态管理 ============

class PipelineState:
    """流水线状态管理器"""
    def __init__(self):
        self.lock = threading.Lock()
        self.reset()
    
    def reset(self):
        self.running = False
        self.paused = False
        self.cancelled = False
        self.current_stage = None
        self.current_item = None
        self.progress = 0
        self.total = 0
        self.stage_progress = 0  # 当前阶段的进度
        self.stage_total = 0
        self.logs = []
        self.articles = []
        self.processes = {}  # stage -> subprocess.Popen
        self.checkpoint = None  # 用于继续任务的检查点
        self.error = None
        self.selected_sources = []  # 用户选择的RSS源
        self.custom_topics = []  # 用户输入的自定义主题
    
    def to_dict(self):
        return {
            'running': self.running,
            'paused': self.paused,
            'cancelled': self.cancelled,
            'current_stage': self.current_stage,
            'current_item': self.current_item,
            'progress': self.progress,
            'total': self.total,
            'stage_progress': self.stage_progress,
            'stage_total': self.stage_total,
            'logs': self.logs[-50:],  # 最近50条日志
            'articles': self.articles,
            'checkpoint': self.checkpoint,
            'error': str(self.error) if self.error else None,
            'selected_sources': self.selected_sources,
            'custom_topics': self.custom_topics
        }

state = PipelineState()
event_queue = queue.Queue()  # SSE 事件队列

# ============ SSE 事件推送 ============

def emit_event(event_type, data):
    """推送 SSE 事件"""
    event = {
        'type': event_type,
        'data': data,
        'timestamp': datetime.now().isoformat()
    }
    event_queue.put(event)
    # 同时更新 state.logs
    if event_type in ['log', 'error']:
        with state.lock:
            state.logs.append({
                'time': datetime.now().strftime('%H:%M:%S'),
                'type': event_type,
                'msg': data.get('msg', '')
            })

def sse_stream():
    """SSE 流生成器"""
    def generate():
        # 先发送当前状态
        with state.lock:
            yield f"event: state\ndata: {json.dumps(state.to_dict())}\n\n"
        
        while True:
            try:
                event = event_queue.get(timeout=30)
                yield f"event: {event['type']}\ndata: {json.dumps(event['data'])}\n\n"
                
                # 如果收到终止信号，结束流
                if event['type'] == 'end':
                    break
            except queue.Empty:
                # 发送心跳
                yield f"event: heartbeat\ndata: {json.dumps({'time': datetime.now().isoformat()})}\n\n"
    
    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )

# ============ OpenClaw 调用 ============

def load_config():
    config_path = Path(__file__).parent / 'config.yaml'
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    return {}

def call_llm_api(prompt, timeout=120):
    """直接调用 LLM API（OpenAI兼容）"""
    import requests
    
    # 从 config.yaml 加载配置
    config = load_config()
    ai_config = config.get('ai', {})
    
    api_url = ai_config.get('base_url', 'http://42.193.169.81:18789/v1/chat/completions')
    if not api_url.endswith('/chat/completions'):
        api_url = api_url.rstrip('/') + '/chat/completions'
    
    api_key = ai_config.get('api_key', 'vinkybbvinkybb')
    model = ai_config.get('model', 'openclaw')
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 4000
    }
    
    try:
        response = requests.post(api_url, headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()
        result = response.json()
        
        if "choices" in result and len(result["choices"]) > 0:
            content = result["choices"][0]["message"]["content"]
            return content, None
        else:
            return None, "no_response"
    except requests.exceptions.Timeout:
        return None, "timeout"
    except Exception as e:
        return None, str(e)

def run_openclaw_stream(prompt, stage='unknown', timeout=120):
    """调用 LLM API 并返回结果"""
    emit_event('log', {'msg': f'🤖 调用 AI ({stage})...', 'stage': stage})
    
    # 检查取消
    with state.lock:
        if state.cancelled:
            return None, "cancelled"
    
    result, error = call_llm_api(prompt, timeout)
    
    if error:
        emit_event('log', {'msg': f'❌ AI调用失败 ({stage}): {error}', 'stage': stage})
        return None, error
    
    # 流式推送结果（按行）
    lines = result.strip().split('\n')
    for line in lines:
        emit_event('stream', {
            'stage': stage,
            'line': line,
            'partial': True
        })
    
    emit_event('stream', {
        'stage': stage,
        'line': result,
        'partial': False
    })
    
    return result, None

def run_module(module_name, *args):
    """运行 Python 模块"""
    result = subprocess.run(
        [sys.executable, '-m', f'modules.{module_name}', *args],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent
    )
    if result.returncode != 0:
        raise Exception(result.stderr)
    return result.stdout

# ============ 流水线阶段 ============

# 前端checkbox值 -> config.yaml中的源名称/URL映射
SOURCE_ALIAS_MAP = {
    'techcrunch': ['TechCrunch', 'techcrunch.com'],
    'hackernews': ['Hacker News', 'hnrss.org'],
    'openai': ['OpenAI', 'openai.com'],
    'baoyu': ['宝玉', 'baoyu'],
    'ruanyifeng': ['阮一峰', 'ruanyifeng'],
}

def normalize_source_selection(selected):
    """将前端选择值转换为config中的名称/URL"""
    normalized = []
    for s in selected:
        # 处理 dict 类型（前端可能传完整对象）
        if isinstance(s, dict):
            name = s.get('name', '')
            url = s.get('url', '')
            # 检查映射表
            if name.lower() in SOURCE_ALIAS_MAP:
                normalized.extend(SOURCE_ALIAS_MAP[name.lower()])
            normalized.extend([name, url])
        else:
            # 字符串类型
            s_str = str(s).lower()
            if s_str in SOURCE_ALIAS_MAP:
                normalized.extend(SOURCE_ALIAS_MAP[s_str])
            normalized.append(s)
    return normalized

def stage_fetch_rss(max_items=10, checkpoint=None):
    """RSS 抓取阶段"""
    emit_event('stage', {'name': 'fetch', 'label': '📡 抓取RSS', 'progress': 0})
    
    with state.lock:
        state.current_stage = 'fetch'
        state.stage_progress = 0
        state.stage_total = 4  # RSS 源数量
        selected = state.selected_sources
        topics = state.custom_topics
    
    config = load_config()
    rss_sources = config.get('rss', {}).get('sources', [])
    
    # 根据用户选择过滤RSS源
    if selected:
        # 将前端值映射到实际源名称/URL（只保留字符串）
        normalized = normalize_source_selection(selected)
        normalized_strs = [str(x) for x in normalized if not isinstance(x, dict)]
        rss_sources = [s for s in rss_sources 
                       if s.get('name') in normalized_strs 
                       or s.get('url') in normalized_strs
                       or any(alias.lower() in s.get('name', '').lower() or alias.lower() in s.get('url', '').lower() 
                              for alias in normalized_strs)]
        emit_event('log', {'msg': f'🎯 已筛选 {len(rss_sources)} 个RSS源', 'stage': 'fetch'})
    
    if checkpoint:
        # 从检查点恢复
        rss_sources = [s for s in rss_sources if s not in checkpoint.get('completed_sources', [])]
    
    all_articles = []
    for i, source in enumerate(rss_sources):
        # 检查取消
        with state.lock:
            if state.cancelled:
                return None, 'cancelled', {'completed_sources': [s['url'] for s in rss_sources[:i]]}
            state.stage_progress = i + 1
            state.current_item = source.get('name', source.get('url', 'unknown'))
        
        emit_event('log', {'msg': f'📡 抓取: {source.get("name", source.get("url", ""))}', 'stage': 'fetch'})
        emit_event('stage', {'name': 'fetch', 'label': '📡 抓取RSS', 'progress': (i+1) / len(rss_sources) * 100})
        
        try:
            output = run_module('rss_fetcher', '--source', source['url'], '--max', str(max_items))
            articles = json.loads(output) if output.strip() else []
            all_articles.extend(articles)
            emit_event('item', {'stage': 'fetch', 'count': len(articles)})
        except Exception as e:
            emit_event('log', {'msg': f'⚠️ 抓取失败: {e}', 'stage': 'fetch', 'level': 'warn'})
    
    # 处理自定义主题
    with state.lock:
        topics = state.custom_topics
    if topics:
        emit_event('log', {'msg': f'💡 添加 {len(topics)} 个自定义主题', 'stage': 'fetch'})
        for topic in topics:
            all_articles.append({
                'title': topic,
                'link': f'custom://{topic}',
                'summary': f'用户自定义主题: {topic}',
                'source': 'custom',
                'published': datetime.now().isoformat()
            })
    
    # 保存到文件
    output_dir = Path(__file__).parent / 'output' / 'raw'
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f'rss_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_articles, f, ensure_ascii=False, indent=2)
    
    emit_event('log', {'msg': f'✅ 抓取完成: {len(all_articles)} 篇文章', 'stage': 'fetch'})
    return all_articles, None, None

def process_single_summary(article, index, total):
    """处理单篇文章的摘要（用于并行）"""
    with state.lock:
        if state.cancelled:
            return None, article, True
        state.stage_progress = index + 1
        state.current_item = article.get('title', '')[:50]
    
    emit_event('log', {'msg': f'📝 摘要: {article.get("title", "")[:30]}...', 'stage': 'summarize'})
    emit_event('stage', {'name': 'summarize', 'label': '📝 AI摘要', 'progress': (index+1) / total * 100})
    
    prompt = f"""请为以下文章生成一个简洁的摘要（100字以内）：

标题: {article.get('title', '')}
内容: {article.get('summary', article.get('description', ''))[:1000]}

只输出摘要内容，不要其他说明。"""
    
    summary, err = run_openclaw_stream(prompt, stage='summarize')
    if err:
        if err == 'cancelled':
            return None, article, True
        emit_event('log', {'msg': f'⚠️ 摘要失败: {err}', 'stage': 'summarize', 'level': 'warn'})
        summary = article.get('summary', '')[:200]
    
    article['ai_summary'] = summary
    emit_event('item', {'stage': 'summarize', 'title': article.get('title', '')[:30]})
    return article, None, False

def stage_summarize(articles, checkpoint=None):
    """AI 摘要阶段 - 并行处理"""
    emit_event('stage', {'name': 'summarize', 'label': '📝 AI摘要', 'progress': 0})
    
    with state.lock:
        state.current_stage = 'summarize'
        state.stage_progress = 0
        state.stage_total = len(articles)
    
    if checkpoint:
        processed_ids = set(checkpoint.get('processed_ids', []))
        articles = [a for a in articles if a.get('link') not in processed_ids]
    
    config = load_config()
    ai_config = config.get('ai', {})
    parallel_workers = ai_config.get('parallel_workers', 3)  # 默认并行3篇
    
    summarized = []
    
    # 使用线程池并行处理
    with ThreadPoolExecutor(max_workers=parallel_workers) as executor:
        futures = {
            executor.submit(process_single_summary, article, i, len(articles)): article
            for i, article in enumerate(articles)
        }
        
        for future in as_completed(futures):
            with state.lock:
                if state.cancelled:
                    executor.shutdown(wait=False, cancel_futures=True)
                    return None, 'cancelled', {'processed_ids': [a['link'] for a in summarized]}
            
            result_article, err, cancelled = future.result()
            if cancelled:
                return None, 'cancelled', {'processed_ids': [a['link'] for a in summarized]}
            if result_article:
                summarized.append(result_article)
    
    emit_event('log', {'msg': f'✅ 摘要完成: {len(summarized)} 篇（并行 {parallel_workers} 线程）', 'stage': 'summarize'})
    return summarized, None, None

def process_single_expand(article, index, total, expand_style):
    """处理单篇文章的扩写（用于并行）"""
    with state.lock:
        if state.cancelled:
            return None, article, True
        state.stage_progress = index + 1
        state.current_item = article.get('title', '')[:50]
    
    emit_event('log', {'msg': f'✍️ 扩写: {article.get("title", "")[:30]}...', 'stage': 'expand'})
    emit_event('stage', {'name': 'expand', 'label': '✍️ AI扩写', 'progress': (index+1) / total * 100})
    
    prompt = f"""请基于以下摘要，扩写一篇完整的博客文章（800-1500字）：

标题: {article.get('title', '')}
摘要: {article.get('ai_summary', article.get('summary', ''))}

要求：
1. 风格: {expand_style}
2. 结构清晰，有开头、正文、结尾
3. 内容有价值，避免空话
4. 直接输出文章内容，使用 Markdown 格式

开始扩写："""
    
    content, err = run_openclaw_stream(prompt, stage='expand', timeout=180)
    if err:
        if err == 'cancelled':
            return None, article, True
        emit_event('log', {'msg': f'⚠️ 扩写失败: {err}', 'stage': 'expand', 'level': 'warn'})
        content = f"# {article.get('title', '')}\n\n{article.get('ai_summary', '扩写失败，请重试。')}"
    
    article['expanded_content'] = content
    
    # 保存文章
    output_dir = Path(__file__).parent / 'output' / 'articles'
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_title = article.get('title', 'untitled').replace('/', '_').replace('\\', '_')[:50]
    output_file = output_dir / f'{datetime.now().strftime("%Y%m%d_%H%M%S")}_{safe_title}.md'
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(content)
    
    emit_event('item', {'stage': 'expand', 'title': article.get('title', '')[:30], 'file': str(output_file)})
    emit_event('article', {'title': article.get('title', ''), 'file': str(output_file)})
    
    return article, None, False

def stage_expand(articles, checkpoint=None):
    """AI 扩写阶段 - 并行处理"""
    emit_event('stage', {'name': 'expand', 'label': '✍️ AI扩写', 'progress': 0})
    
    with state.lock:
        state.current_stage = 'expand'
        state.stage_progress = 0
        state.stage_total = len(articles)
    
    if checkpoint:
        expanded_titles = set(checkpoint.get('expanded_titles', []))
        articles = [a for a in articles if a.get('title') not in expanded_titles]
    
    config = load_config()
    ai_config = config.get('ai', {})
    expand_style = ai_config.get('expand_style', '技术博客风格')
    parallel_workers = ai_config.get('parallel_workers', 3)  # 默认并行3篇
    
    expanded_articles = []
    
    # 使用线程池并行处理
    with ThreadPoolExecutor(max_workers=parallel_workers) as executor:
        futures = {
            executor.submit(process_single_expand, article, i, len(articles), expand_style): article
            for i, article in enumerate(articles)
        }
        
        for future in as_completed(futures):
            with state.lock:
                if state.cancelled:
                    executor.shutdown(wait=False, cancel_futures=True)
                    return None, 'cancelled', {'expanded_titles': [a['title'] for a in expanded_articles]}
            
            result_article, err, cancelled = future.result()
            if cancelled:
                return None, 'cancelled', {'expanded_titles': [a['title'] for a in expanded_articles]}
            if result_article:
                expanded_articles.append(result_article)
    
    emit_event('log', {'msg': f'✅ 扩写完成: {len(expanded_articles)} 篇（并行 {parallel_workers} 线程）', 'stage': 'expand'})
    return expanded_articles, None, None

def stage_publish(articles, checkpoint=None):
    """发布阶段"""
    emit_event('stage', {'name': 'publish', 'label': '📤 发布文章', 'progress': 0})
    
    with state.lock:
        state.current_stage = 'publish'
        state.stage_progress = 0
        state.stage_total = len(articles)
    
    published_count = 0
    for i, article in enumerate(articles):
        with state.lock:
            if state.cancelled:
                return published_count, 'cancelled', None
            state.stage_progress = i + 1
            state.current_item = article.get('title', '')[:50]
        
        emit_event('log', {'msg': f'📤 发布: {article.get("title", "")[:30]}...', 'stage': 'publish'})
        emit_event('stage', {'name': 'publish', 'label': '📤 发布文章', 'progress': (i+1) / len(articles) * 100})
        
        try:
            run_module('publisher', '--file', article.get('file', ''))
            published_count += 1
            emit_event('item', {'stage': 'publish', 'title': article.get('title', '')[:30]})
        except Exception as e:
            emit_event('log', {'msg': f'⚠️ 发布失败: {e}', 'stage': 'publish', 'level': 'warn'})
    
    emit_event('log', {'msg': f'✅ 发布完成: {published_count} 篇', 'stage': 'publish'})
    return published_count, None, None

# ============ 流水线控制 ============

def run_pipeline_full(checkpoint=None):
    """运行完整流水线"""
    with state.lock:
        state.running = True
        state.cancelled = False
        state.error = None
        if checkpoint:
            state.checkpoint = checkpoint
    
    try:
        emit_event('start', {'msg': '🚀 流水线启动', 'checkpoint': checkpoint is not None})
        
        # 阶段1: RSS 抓取
        articles, err, cp = stage_fetch_rss(checkpoint=checkpoint)
        if err == 'cancelled':
            with state.lock:
                state.checkpoint = {'stage': 'fetch', 'data': cp}
            emit_event('cancelled', {'msg': '⚠️ 流水线已取消', 'checkpoint': state.checkpoint})
            return
        if not articles:
            emit_event('log', {'msg': '⚠️ 未抓取到文章', 'stage': 'fetch'})
            emit_event('end', {'msg': '流水线结束（无文章）'})
            return
        
        with state.lock:
            state.progress = 1
            state.total = 4
            state.articles = articles
        
        # 阶段2: AI 摘要
        articles, err, cp = stage_summarize(articles, checkpoint=checkpoint)
        if err == 'cancelled':
            with state.lock:
                state.checkpoint = {'stage': 'summarize', 'data': cp}
            emit_event('cancelled', {'msg': '⚠️ 流水线已取消', 'checkpoint': state.checkpoint})
            return
        
        with state.lock:
            state.progress = 2
        
        # 阶段3: AI 扩写
        articles, err, cp = stage_expand(articles, checkpoint=checkpoint)
        if err == 'cancelled':
            with state.lock:
                state.checkpoint = {'stage': 'expand', 'data': cp}
            emit_event('cancelled', {'msg': '⚠️ 流水线已取消', 'checkpoint': state.checkpoint})
            return
        
        with state.lock:
            state.progress = 3
            state.articles = articles
        
        # 阶段4: 发布
        published, err, _ = stage_publish(articles, checkpoint=checkpoint)
        if err == 'cancelled':
            emit_event('cancelled', {'msg': '⚠️ 流水线已取消'})
            return
        
        with state.lock:
            state.progress = 4
        
        emit_event('complete', {
            'msg': '🎉 流水线完成!',
            'articles': len(articles),
            'published': published
        })
        
    except Exception as e:
        with state.lock:
            state.error = e
        emit_event('error', {'msg': f'❌ 错误: {str(e)}'})
    
    finally:
        with state.lock:
            state.running = False
        emit_event('end', {})

# ============ API 路由 ============

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/stream')
def api_stream():
    """SSE 流式事件端点"""
    return sse_stream()

@app.route('/api/rss-sources')
def api_rss_sources():
    """获取RSS源列表"""
    config = load_config()
    sources = config.get('rss', {}).get('sources', [])
    return jsonify({'sources': sources})

@app.route('/api/pipeline', methods=['POST'])
def api_pipeline():
    """启动完整流水线"""
    with state.lock:
        if state.running:
            return jsonify({'error': '流水线正在运行中'}), 400
        state.reset()
        state.running = True
    
    # 接收前端传来的 sources 和 topics
    data = request.get_json() or {}
    sources = data.get('sources', [])
    topics = data.get('topics', [])
    
    # 保存到 state 供流水线使用
    with state.lock:
        state.selected_sources = sources
        state.custom_topics = topics
    
    emit_event('log', {'msg': f'📋 已选择 {len(sources)} 个RSS源, {len(topics)} 个自定义主题', 'stage': 'init'})
    
    # 在后台线程运行
    thread = threading.Thread(target=run_pipeline_full)
    thread.daemon = True
    thread.start()
    
    return jsonify({'status': 'started', 'sources': len(sources), 'topics': len(topics)})

@app.route('/api/resume', methods=['POST'])
def api_resume():
    """继续被取消的任务"""
    with state.lock:
        if state.running:
            return jsonify({'error': '流水线正在运行中'}), 400
        if not state.checkpoint:
            return jsonify({'error': '没有可继续的检查点'}), 400
        
        checkpoint = state.checkpoint
        state.reset()
        state.running = True
    
    thread = threading.Thread(target=run_pipeline_full, kwargs={'checkpoint': checkpoint})
    thread.daemon = True
    thread.start()
    
    return jsonify({'status': 'resumed', 'checkpoint': checkpoint})

@app.route('/api/cancel', methods=['POST'])
def api_cancel():
    """取消当前任务"""
    with state.lock:
        if not state.running:
            return jsonify({'error': '没有运行中的任务'}), 400
        state.cancelled = True
        
        # 终止所有进程
        for stage, proc in state.processes.items():
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                emit_event('log', {'msg': f'🛑 终止进程: {stage}', 'stage': stage})
            except:
                pass
    
    return jsonify({'status': 'cancelled'})

@app.route('/api/status')
def api_status():
    """获取当前状态"""
    with state.lock:
        return jsonify(state.to_dict())

@app.route('/api/fetch', methods=['POST'])
def api_fetch():
    """单独运行 RSS 抓取"""
    with state.lock:
        if state.running:
            return jsonify({'error': '流水线正在运行中'}), 400
        state.reset()
        state.running = True
    
    def run():
        try:
            articles, err, _ = stage_fetch_rss(max_items=request.json.get('max_items', 10))
            with state.lock:
                state.articles = articles
                state.running = False
            emit_event('complete', {'articles': len(articles) if articles else 0})
            emit_event('end', {})
        except Exception as e:
            with state.lock:
                state.error = e
                state.running = False
            emit_event('error', {'msg': str(e)})
            emit_event('end', {})
    
    thread = threading.Thread(target=run)
    thread.daemon = True
    thread.start()
    
    return jsonify({'status': 'started'})

@app.route('/api/expand', methods=['POST'])
def api_expand():
    """单独运行 AI 扩写"""
    with state.lock:
        if state.running:
            return jsonify({'error': '流水线正在运行中'}), 400
        
        # 检查是否有已抓取的文章
        if not state.articles:
            # 尝试从文件加载
            raw_dir = Path(__file__).parent / 'output' / 'raw'
            if raw_dir.exists():
                files = sorted(raw_dir.glob('*.json'), reverse=True)
                if files:
                    with open(files[0], 'r', encoding='utf-8') as f:
                        state.articles = json.load(f)
        
        if not state.articles:
            return jsonify({'error': '没有可扩写的文章，请先抓取 RSS'}), 400
        
        state.reset()
        state.running = True
    
    def run():
        try:
            articles, err, _ = stage_summarize(state.articles)
            if not err:
                articles, err, _ = stage_expand(articles)
            with state.lock:
                state.articles = articles
                state.running = False
            emit_event('complete', {'articles': len(articles) if articles else 0})
            emit_event('end', {})
        except Exception as e:
            with state.lock:
                state.error = e
                state.running = False
            emit_event('error', {'msg': str(e)})
            emit_event('end', {})
    
    thread = threading.Thread(target=run)
    thread.daemon = True
    thread.start()
    
    return jsonify({'status': 'started'})

@app.route('/api/publish', methods=['POST'])
def api_publish():
    """单独运行发布"""
    with state.lock:
        if state.running:
            return jsonify({'error': '流水线正在运行中'}), 400
        state.running = True
    
    def run():
        try:
            articles_dir = Path(__file__).parent / 'output' / 'articles'
            articles = [{'title': f.stem, 'file': f.name} for f in articles_dir.glob('*.md')]
            published, _, _ = stage_publish(articles)
            with state.lock:
                state.running = False
            emit_event('complete', {'published': published})
            emit_event('end', {})
        except Exception as e:
            with state.lock:
                state.error = e
                state.running = False
            emit_event('error', {'msg': str(e)})
            emit_event('end', {})
    
    thread = threading.Thread(target=run)
    thread.daemon = True
    thread.start()
    
    return jsonify({'status': 'started'})

@app.route('/api/articles')
def api_articles():
    """获取已生成的文章列表"""
    articles_dir = Path(__file__).parent / 'output' / 'articles'
    articles = []
    if articles_dir.exists():
        for f in sorted(articles_dir.glob('*.md'), reverse=True)[:20]:
            content = f.read_text(encoding='utf-8')
            title = content.split('\n')[0].replace('#', '').strip() or f.stem
            preview = content[:200].replace('\n', ' ')
            articles.append({
                'title': title,
                'file': f.name,
                'preview': preview,
                'date': datetime.fromtimestamp(f.stat().st_mtime).strftime('%Y-%m-%d %H:%M'),
                'status': '草稿'
            })
    return jsonify({'articles': articles})


@app.route('/api/articles/<path:filename>', methods=['GET'])
def api_get_article(filename):
    """获取单篇文章内容"""
    try:
        article_path = Path(__file__).parent / 'output' / 'articles' / filename
        if not article_path.exists():
            article_path = Path(filename)

        if not article_path.exists():
            return jsonify({'error': '文件不存在'}), 404

        content = article_path.read_text(encoding='utf-8')
        lines = content.split('\n')
        title = lines[0].replace('# ', '').replace('#', '') if lines else '无标题'

        return jsonify({
            'filename': filename,
            'title': title,
            'content': content,
            'preview': content[:500]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/articles/<path:filename>', methods=['DELETE'])
def api_delete_article(filename):
    """删除文章"""
    try:
        article_path = Path(__file__).parent / 'output' / 'articles' / filename
        if not article_path.exists():
            # 可能是完整路径
            article_path = Path(filename)
        
        if article_path.exists() and article_path.is_file():
            article_path.unlink()
            return jsonify({'status': 'deleted', 'file': str(article_path)})
        else:
            return jsonify({'error': '文件不存在'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/articles/<path:filename>', methods=['PUT'])
def api_update_article(filename):
    """更新文章内容"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': '无数据'}), 400
        
        article_path = Path(__file__).parent / 'output' / 'articles' / filename
        if not article_path.exists():
            article_path = Path(filename)
        
        if not article_path.exists():
            return jsonify({'error': '文件不存在'}), 404
        
        content = article_path.read_text(encoding='utf-8')
        
        # 根据字段更新内容
        if 'title' in data:
            lines = content.split('\n')
            lines[0] = f"# {data['title']}"
            content = '\n'.join(lines)
        
        if 'content' in data:
            # 替换正文内容（保留标题和元数据）
            lines = content.split('\n')
            title_line = lines[0] if lines else ''
            content = title_line + '\n\n' + data['content']
        
        if 'raw_content' in data:
            # 直接替换全部内容
            content = data['raw_content']
        
        article_path.write_text(content, encoding='utf-8')
        return jsonify({'status': 'updated', 'file': str(article_path)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/channels')
def api_get_channels():
    """获取可用的发布渠道"""
    channels = []
    config = load_config()
    publish_config = config.get('publish', {})
    
    if publish_config.get('local', {}).get('enabled'):
        channels.append({
            'id': 'local',
            'name': '本地博客',
            'type': 'local',
            'path': publish_config['local'].get('output_dir', '')
        })
    
    if publish_config.get('github', {}).get('enabled'):
        channels.append({
            'id': 'github',
            'name': 'GitHub Pages',
            'type': 'github',
            'repo': publish_config['github'].get('repo', '')
        })
    
    if publish_config.get('wordpress', {}).get('enabled'):
        channels.append({
            'id': 'wordpress',
            'name': 'WordPress',
            'type': 'wordpress',
            'url': publish_config['wordpress'].get('url', '')
        })
    
    if publish_config.get('webhook', {}).get('enabled'):
        channels.append({
            'id': 'webhook',
            'name': 'Webhook',
            'type': 'webhook'
        })
    
    return jsonify({'channels': channels})


@app.route('/api/publish/<path:filename>', methods=['POST'])
def api_publish_article(filename):
    """发布文章到指定渠道"""
    try:
        data = request.get_json() or {}
        channels = data.get('channels', ['local'])
        
        article_path = Path(__file__).parent / 'output' / 'articles' / filename
        if not article_path.exists():
            article_path = Path(filename)
        
        if not article_path.exists():
            return jsonify({'error': '文章不存在'}), 404
        
        content = article_path.read_text(encoding='utf-8')
        results = []
        
        from modules.publisher import publish_article
        
        for channel in channels:
            try:
                result = publish_article(content, channel)
                results.append({'channel': channel, 'status': 'success', 'result': result})
            except Exception as e:
                results.append({'channel': channel, 'status': 'error', 'error': str(e)})
        
        return jsonify({'results': results})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/chat', methods=['POST'])
def api_chat():
    """AI聊天接口 - 用于修改文章"""
    try:
        data = request.get_json()
        message = data.get('message', '')
        article_content = data.get('article_content', '')
        article_filename = data.get('article_filename', '')
        history = data.get('history', [])
        
        # 构建系统提示
        system_prompt = """你是一个专业的文章编辑助手。用户会给你一篇文章，然后告诉你需要修改什么。
你可以：
1. 修改文章的标题、内容
2. 调整文章结构
3. 润色语言
4. 添加或删除段落

当用户要求修改时，请直接返回修改后的完整文章内容，用 ```markdown 包裹。
如果用户只是问问题，正常回答即可。"""

        # 构建消息
        messages = [
            {"role": "system", "content": system_prompt},
        ]
        
        if article_content:
            messages.append({
                "role": "user", 
                "content": f"这是当前文章内容：\n\n{article_content}\n\n请记住这篇文章，后续我会要求修改。"
            })
            messages.append({
                "role": "assistant",
                "content": "好的，我已经记住了这篇文章。请告诉我需要怎么修改。"
            })
        
        # 添加历史消息
        for h in history[-10:]:  # 保留最近10条
            messages.append({"role": h.get('role', 'user'), "content": h.get('content', '')})
        
        # 添加当前消息
        messages.append({"role": "user", "content": message})
        
        # 调用AI
        from modules.openclaw_client import call_openclaw
        response = call_openclaw(messages, task_type='chat')
        
        return jsonify({'response': response})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/articles/<path:filename>/regenerate', methods=['POST'])
def api_regenerate_article_section(filename):
    """重新生成文章的某个部分（摘要、扩写、配图）"""
    try:
        data = request.get_json()
        section = data.get('section')  # 'summary', 'expand', 'image'
        
        article_path = Path(__file__).parent / 'output' / 'articles' / filename
        if not article_path.exists():
            article_path = Path(filename)
        
        if not article_path.exists():
            return jsonify({'error': '文件不存在'}), 404
        
        content = article_path.read_text(encoding='utf-8')
        
        if section == 'image':
            # 重新生成配图
            from modules.image_gen import generate_image_for_article
            image_result = generate_image_for_article(content)
            if image_result:
                return jsonify({'status': 'regenerated', 'section': 'image', 'url': image_result})
            else:
                return jsonify({'error': '配图生成失败'}), 500
        
        elif section == 'expand':
            # 重新扩写
            from modules.expander import expand_article
            # 提取原文部分
            expand_result = expand_article(content)
            if expand_result:
                return jsonify({'status': 'regenerated', 'section': 'expand'})
            else:
                return jsonify({'error': '扩写失败'}), 500
        
        else:
            return jsonify({'error': '未知部分'}), 400
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
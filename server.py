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
            'error': str(self.error) if self.error else None
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

def run_openclaw_stream(prompt, stage='unknown', timeout=120):
    """运行 OpenClaw 并流式输出结果"""
    emit_event('log', {'msg': f'🤖 调用 OpenClaw ({stage})...', 'stage': stage})
    
    try:
        proc = subprocess.Popen(
            ['openclaw', 'ask', '--model', 'custom-coding-dashscope-aliyuncs-com/glm-5', prompt],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            preexec_fn=os.setsid  # 创建新的进程组，便于取消
        )
        
        with state.lock:
            state.processes[stage] = proc
        
        output_lines = []
        start_time = time.time()
        
        while True:
            # 检查取消
            with state.lock:
                if state.cancelled:
                    emit_event('log', {'msg': f'⚠️ 任务已取消 ({stage})', 'stage': stage})
                    try:
                        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                    except:
                        pass
                    return None, "cancelled"
            
            # 检查超时
            if time.time() - start_time > timeout:
                proc.terminate()
                return None, "timeout"
            
            # 读取输出
            line = proc.stdout.readline()
            if line:
                line = line.strip()
                if line:
                    output_lines.append(line)
                    # 流式推送每一行
                    emit_event('stream', {
                        'stage': stage,
                        'line': line,
                        'partial': True
                    })
            
            # 检查进程结束
            if proc.poll() is not None:
                # 读取剩余输出
                remaining = proc.stdout.read()
                if remaining:
                    for l in remaining.strip().split('\n'):
                        if l:
                            output_lines.append(l)
                            emit_event('stream', {
                                'stage': stage,
                                'line': l,
                                'partial': False
                            })
                break
            
            time.sleep(0.01)
        
        # 清理进程引用
        with state.lock:
            state.processes.pop(stage, None)
        
        if proc.returncode != 0:
            stderr = proc.stderr.read()
            return None, f"Error: {stderr}"
        
        return '\n'.join(output_lines), None
        
    except Exception as e:
        return None, str(e)

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

def stage_fetch_rss(max_items=10, checkpoint=None):
    """RSS 抓取阶段"""
    emit_event('stage', {'name': 'fetch', 'label': '📡 抓取RSS', 'progress': 0})
    
    with state.lock:
        state.current_stage = 'fetch'
        state.stage_progress = 0
        state.stage_total = 4  # RSS 源数量
    
    config = load_config()
    rss_sources = config.get('rss', {}).get('sources', [])
    
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
    
    # 保存到文件
    output_dir = Path(__file__).parent / 'output' / 'raw'
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f'rss_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_articles, f, ensure_ascii=False, indent=2)
    
    emit_event('log', {'msg': f'✅ 抓取完成: {len(all_articles)} 篇文章', 'stage': 'fetch'})
    return all_articles, None, None

def stage_summarize(articles, checkpoint=None):
    """AI 摘要阶段"""
    emit_event('stage', {'name': 'summarize', 'label': '📝 AI摘要', 'progress': 0})
    
    with state.lock:
        state.current_stage = 'summarize'
        state.stage_progress = 0
        state.stage_total = len(articles)
    
    if checkpoint:
        # 跳过已处理的
        processed_ids = set(checkpoint.get('processed_ids', []))
        articles = [a for a in articles if a.get('link') not in processed_ids]
    
    summarized = []
    for i, article in enumerate(articles):
        with state.lock:
            if state.cancelled:
                return None, 'cancelled', {'processed_ids': [a['link'] for a in summarized]}
            state.stage_progress = i + 1
            state.current_item = article.get('title', '')[:50]
        
        emit_event('log', {'msg': f'📝 摘要: {article.get("title", "")[:30]}...', 'stage': 'summarize'})
        emit_event('stage', {'name': 'summarize', 'label': '📝 AI摘要', 'progress': (i+1) / len(articles) * 100})
        
        prompt = f"""请为以下文章生成一个简洁的摘要（100字以内）：

标题: {article.get('title', '')}
内容: {article.get('summary', article.get('description', ''))[:1000]}

只输出摘要内容，不要其他说明。"""
        
        summary, err = run_openclaw_stream(prompt, stage='summarize')
        if err:
            if err == 'cancelled':
                return None, 'cancelled', {'processed_ids': [a['link'] for a in summarized]}
            emit_event('log', {'msg': f'⚠️ 摘要失败: {err}', 'stage': 'summarize', 'level': 'warn'})
            summary = article.get('summary', '')[:200]
        
        article['ai_summary'] = summary
        summarized.append(article)
        emit_event('item', {'stage': 'summarize', 'title': article.get('title', '')[:30]})
    
    emit_event('log', {'msg': f'✅ 摘要完成: {len(summarized)} 篇', 'stage': 'summarize'})
    return summarized, None, None

def stage_expand(articles, checkpoint=None):
    """AI 扩写阶段"""
    emit_event('stage', {'name': 'expand', 'label': '✍️ AI扩写', 'progress': 0})
    
    with state.lock:
        state.current_stage = 'expand'
        state.stage_progress = 0
        state.stage_total = len(articles)
    
    if checkpoint:
        expanded_titles = set(checkpoint.get('expanded_titles', []))
        articles = [a for a in articles if a.get('title') not in expanded_titles]
    
    expanded_articles = []
    for i, article in enumerate(articles):
        with state.lock:
            if state.cancelled:
                return None, 'cancelled', {'expanded_titles': [a['title'] for a in expanded_articles]}
            state.stage_progress = i + 1
            state.current_item = article.get('title', '')[:50]
        
        emit_event('log', {'msg': f'✍️ 扩写: {article.get("title", "")[:30]}...', 'stage': 'expand'})
        emit_event('stage', {'name': 'expand', 'label': '✍️ AI扩写', 'progress': (i+1) / len(articles) * 100})
        
        config = load_config()
        ai_config = config.get('ai', {})
        expand_style = ai_config.get('expand_style', '技术博客风格')
        
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
                return None, 'cancelled', {'expanded_titles': [a['title'] for a in expanded_articles]}
            emit_event('log', {'msg': f'⚠️ 扩写失败: {err}', 'stage': 'expand', 'level': 'warn'})
            content = f"# {article.get('title', '')}\n\n{article.get('ai_summary', '扩写失败，请重试。')}"
        
        article['expanded_content'] = content
        expanded_articles.append(article)
        
        # 保存文章
        output_dir = Path(__file__).parent / 'output' / 'articles'
        output_dir.mkdir(parents=True, exist_ok=True)
        safe_title = article.get('title', 'untitled').replace('/', '_').replace('\\', '_')[:50]
        output_file = output_dir / f'{datetime.now().strftime("%Y%m%d_%H%M%S")}_{safe_title}.md'
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        emit_event('item', {'stage': 'expand', 'title': article.get('title', '')[:30], 'file': str(output_file)})
        emit_event('article', {'title': article.get('title', ''), 'file': str(output_file)})
    
    emit_event('log', {'msg': f'✅ 扩写完成: {len(expanded_articles)} 篇', 'stage': 'expand'})
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

@app.route('/api/pipeline', methods=['POST'])
def api_pipeline():
    """启动完整流水线"""
    with state.lock:
        if state.running:
            return jsonify({'error': '流水线正在运行中'}), 400
        state.reset()
        state.running = True
    
    # 在后台线程运行
    thread = threading.Thread(target=run_pipeline_full)
    thread.daemon = True
    thread.start()
    
    return jsonify({'status': 'started'})

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
            articles = [{'title': f.stem, 'file': str(f)} for f in articles_dir.glob('*.md')]
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
                'file': str(f),
                'preview': preview,
                'date': datetime.fromtimestamp(f.stat().st_mtime).strftime('%Y-%m-%d %H:%M'),
                'status': '草稿'
            })
    return jsonify({'articles': articles})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True, threaded=True)
#!/usr/bin/env python3
"""
Blog Pipeline Web Dashboard Server
"""

import os
import sys
import logging
import threading
import re
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, jsonify, request, send_from_directory
from urllib.parse import unquote

BASE_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = BASE_DIR / 'output'
sys.path.insert(0, str(BASE_DIR))

from app import BlogPipeline
from modules.publisher import Publisher

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='static', static_url_path='/static')

pipeline_state = {
    'status': 'idle',
    'progress': 0,
    'articles_processed': 0,
    'total_articles': 0,
    'last_run': None,
    'error': None,
    'log_messages': [],
    'publish_status': {
        'active': False,
        'total': 0,
        'processed': 0,
        'current_article': '',
        'results': []
    }
}

state_lock = threading.Lock()
pipeline = None

def get_pipeline():
    global pipeline
    if pipeline is None:
        try:
            pipeline = BlogPipeline('config.yaml')
        except Exception as e:
            logger.error(f"Failed to initialize pipeline: {e}")
            return None
    return pipeline

def add_log(message, level='info'):
    with state_lock:
        pipeline_state['log_messages'].append({
            'time': datetime.now().strftime('%H:%M:%S'),
            'message': message,
            'level': level
        })
        if len(pipeline_state['log_messages']) > 100:
            pipeline_state['log_messages'] = pipeline_state['log_messages'][-100:]

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/preview/<article_id>')
def preview(article_id):
    return render_template('preview.html', article_id=article_id)

@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)

@app.route('/output/<path:filename>')
def output_files(filename):
    return send_from_directory(str(OUTPUT_DIR), filename)

@app.route('/api/status')
def api_status():
    with state_lock:
        return jsonify({
            'status': pipeline_state['status'],
            'progress': pipeline_state['progress'],
            'articles_processed': pipeline_state['articles_processed'],
            'total_articles': pipeline_state['total_articles'],
            'last_run': pipeline_state['last_run'],
            'error': pipeline_state['error'],
            'publish_status': pipeline_state['publish_status']
        })

@app.route('/api/articles')
def api_articles():
    articles = []
    search_dirs = [OUTPUT_DIR, OUTPUT_DIR / 'articles', OUTPUT_DIR / 'posts', OUTPUT_DIR / 'raw']
    
    all_md_files = []
    for search_dir in search_dirs:
        if search_dir.exists():
            for md_file in search_dir.iterdir():
                if md_file.suffix == '.md' and md_file.is_file():
                    all_md_files.append(md_file)
    
    for md_file in sorted(all_md_files, key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            content = md_file.read_text(encoding='utf-8')
            lines = content.split('\n')
            title = md_file.stem
            status = 'unpublished'
            
            for line in lines[:3]:
                if line.lower().startswith('status: published'):
                    status = 'published'
                elif line.lower().startswith('status: unpublished'):
                    status = 'unpublished'
            
            for line in lines:
                stripped = line.strip()
                if stripped.startswith('#'):
                    title = stripped.replace('#', '').strip()
                    break
            
            stat = md_file.stat()
            articles.append({
                'id': md_file.stem,
                'title': title,
                'file': md_file.name,
                'size': stat.st_size,
                'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M'),
                'status': status
            })
        except Exception as e:
            logger.error(f"Error reading {md_file}: {e}")
    
    return jsonify({'articles': articles, 'total': len(articles)})


@app.route('/api/articles/<filename>', methods=['PUT'])
def api_update_article(filename):
    """Update article content - allow empty content"""
    filename = unquote(filename)
    data = request.get_json() or {}
    
    search_dirs = [OUTPUT_DIR, OUTPUT_DIR / 'articles', OUTPUT_DIR / 'posts', OUTPUT_DIR / 'raw']
    
    for search_dir in search_dirs:
        article_path = search_dir / filename
        if article_path.exists() and article_path.is_file():
            try:
                content = data.get('content', '')
                title = data.get('title', '')
                
                # Allow empty content - just save whatever is provided
                if title:
                    lines = content.split('\n')
                    if lines and lines[0].strip().startswith('#'):
                        lines[0] = f"# {title}"
                        content = '\n'.join(lines)
                
                article_path.write_text(content, encoding='utf-8')
                logger.info(f"Updated article: {filename}")
                return jsonify({'status': 'success', 'message': 'Article saved'})
            except Exception as e:
                logger.error(f"Update failed: {e}")
                return jsonify({'status': 'error', 'message': str(e)}), 500
    
    return jsonify({'status': 'error', 'message': 'Article not found'}), 404


@app.route('/api/articles/<filename>', methods=['DELETE'])
def api_delete_article(filename):
    filename = unquote(filename)
    search_dirs = [OUTPUT_DIR, OUTPUT_DIR / 'articles', OUTPUT_DIR / 'posts', OUTPUT_DIR / 'raw']
    
    for search_dir in search_dirs:
        article_path = search_dir / filename
        if article_path.exists() and article_path.is_file():
            try:
                article_path.unlink()
                logger.info(f"Deleted article: {filename}")
                return jsonify({'success': True, 'message': f'Deleted {filename}'})
            except Exception as e:
                logger.error(f"Delete failed: {e}")
                return jsonify({'error': str(e)}), 500
    
    return jsonify({'error': 'Article not found'}), 404


@app.route('/api/rss-sources')
def api_rss_sources():
    config_path = Path('config.yaml')
    sources = []
    
    if config_path.exists():
        try:
            import yaml
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}
            
            for source in config.get('sources', []):
                sources.append({
                    'name': source.get('name', 'Unknown'),
                    'url': source.get('url', ''),
                    'category': source.get('category', 'general'),
                    'enabled': source.get('enabled', True),
                    'type': source.get('type', 'rss')
                })
        except Exception as e:
            logger.error(f"Error loading config: {e}")
    
    return jsonify({'sources': sources, 'total': len(sources)})

@app.route('/api/logs')
def api_logs():
    with state_lock:
        return jsonify({'logs': pipeline_state['log_messages'][-50:]})

def get_publisher():
    """获取 Publisher 实例"""
    import yaml
    config_path = Path('config.yaml')
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
        return Publisher(config.get('publish', {}))
    return Publisher({})

def publish_article_to_github(filepath: Path, title: str, content: str, tags: list = None) -> dict:
    """
    发布单篇文章到 GitHub
    返回发布结果
    """
    try:
        publisher = get_publisher()
        github_config = publisher.config.get('github', {})
        
        if not github_config.get('enabled', False):
            return {'success': False, 'error': 'GitHub 发布未启用'}
        
        # 调用 GitHub 发布方法
        result = publisher._publish_github(title, content, tags or [])
        
        if result.get('success'):
            # 更新文章状态为已发布
            update_article_status(filepath, 'published')
        
        return result
    except Exception as e:
        logger.error(f"Publish to GitHub failed: {e}")
        return {'success': False, 'error': str(e)}

def update_article_status(filepath: Path, status: str):
    """更新文章的发布状态"""
    try:
        content = filepath.read_text(encoding='utf-8')
        lines = content.split('\n')
        
        # 检查是否有 front matter（支持 --- 或 -- 开头）
        first_line = lines[0].strip() if lines else ''
        has_front_matter = first_line in ('---', '--')
        
        if has_front_matter:
            # 在 front matter 中添加/更新 status
            front_matter_end = None
            delimiter = first_line
            for i, line in enumerate(lines[1:], 1):
                if line.strip() == delimiter:
                    front_matter_end = i
                    break
            
            if front_matter_end:
                # 检查是否已有 status 行
                status_line_idx = None
                for i in range(1, front_matter_end):
                    if lines[i].lower().startswith('status:'):
                        status_line_idx = i
                        break
                
                if status_line_idx:
                    lines[status_line_idx] = f"status: {status}"
                else:
                    lines.insert(front_matter_end, f"status: {status}")
                
                filepath.write_text('\n'.join(lines), encoding='utf-8')
            else:
                # front matter 不完整，添加完整的
                new_content = f"---\nstatus: {status}\n---\n{content}"
                filepath.write_text(new_content, encoding='utf-8')
        else:
            # 添加完整的 front matter
            new_content = f"---\nstatus: {status}\n---\n{content}"
            filepath.write_text(new_content, encoding='utf-8')
        
        logger.info(f"Updated article status: {filepath.name} -> {status}")
    except Exception as e:
        logger.error(f"Update status failed: {e}")

@app.route('/api/pipeline', methods=['POST'])
def api_run_pipeline():
    global pipeline_state
    
    with state_lock:
        if pipeline_state['status'] == 'running':
            return jsonify({'error': 'Pipeline already running'}), 400
        
        pipeline_state['status'] = 'running'
        pipeline_state['progress'] = 0
        pipeline_state['articles_processed'] = 0
        pipeline_state['error'] = None
        pipeline_state['log_messages'] = []
    
    def run_pipeline_thread():
        global pipeline_state
        try:
            add_log('Starting pipeline...', 'info')
            
            p = get_pipeline()
            if not p:
                raise Exception('Pipeline not initialized')
            
            # 检查是否启用 GitHub 自动发布
            import yaml
            config_path = Path('config.yaml')
            auto_publish = False
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f) or {}
                auto_publish = config.get('publish', {}).get('github', {}).get('auto_publish', False)
            
            if auto_publish:
                add_log('GitHub auto-publish enabled', 'info')
            
            add_log('Fetching RSS articles...', 'info')
            articles = p.fetch_articles()
            
            with state_lock:
                pipeline_state['total_articles'] = len(articles)
            
            if not articles:
                add_log('No articles found', 'warning')
                with state_lock:
                    pipeline_state['status'] = 'idle'
                    pipeline_state['progress'] = 100
                return
            
            add_log(f'Found {len(articles)} articles to process', 'info')
            
            processed = 0
            published_count = 0
            for article in articles:
                with state_lock:
                    if pipeline_state['status'] == 'cancelled':
                        add_log('Pipeline stopped by user', 'warning')
                        return
                
                try:
                    title = article.get('title', 'Unknown')
                    add_log(f'Processing: {title[:50]}...', 'info')
                    
                    result = p.process_article(article)
                    
                    if result.get('article', {}).get('success'):
                        md_content = result.get('markdown', '')
                        if md_content:
                            safe_title = "".join(c if c.isalnum() or c in (' ', '-', '_') else '' for c in title)
                            safe_title = safe_title.strip().replace(' ', '_')[:30]
                            filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{safe_title}.md"
                            if not safe_title:
                                filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_untitled.md"
                            output_path = OUTPUT_DIR / filename
                            output_path.write_text(md_content, encoding='utf-8')
                            add_log(f'Saved: {filename}', 'success')
                            
                            # 自动发布到 GitHub
                            if auto_publish:
                                add_log(f'Publishing to GitHub: {title[:30]}...', 'info')
                                tags = result.get('article', {}).get('tags', [])
                                pub_result = publish_article_to_github(output_path, title, md_content, tags)
                                if pub_result.get('success'):
                                    published_count += 1
                                    add_log(f'Published to GitHub: {pub_result.get("url", "")}', 'success')
                                else:
                                    add_log(f'GitHub publish failed: {pub_result.get("error", "unknown")}', 'warning')
                    
                    processed += 1
                    with state_lock:
                        pipeline_state['articles_processed'] = processed
                        pipeline_state['progress'] = int(processed / len(articles) * 100)
                    
                except Exception as e:
                    add_log(f'Error processing article: {str(e)[:50]}', 'error')
            
            add_log(f'Pipeline completed! Processed {processed}, Published {published_count} to GitHub', 'success')
            with state_lock:
                pipeline_state['status'] = 'idle'
                pipeline_state['progress'] = 100
                pipeline_state['last_run'] = datetime.now().isoformat()
                
        except Exception as e:
            add_log(f'Pipeline error: {str(e)}', 'error')
            with state_lock:
                pipeline_state['status'] = 'error'
                pipeline_state['error'] = str(e)
    
    thread = threading.Thread(target=run_pipeline_thread)
    thread.daemon = True
    thread.start()
    
    return jsonify({'status': 'started', 'message': 'Pipeline started in background'})

@app.route('/api/cancel', methods=['POST'])
def api_cancel():
    with state_lock:
        if pipeline_state['status'] == 'running':
            pipeline_state['status'] = 'cancelled'
            add_log('Pipeline cancelled by user', 'warning')
            return jsonify({'status': 'cancelled'})
        
    return jsonify({'error': 'No running pipeline'}), 400

@app.route('/api/article/<article_id>')
def api_article_detail(article_id):
    md_files = list(OUTPUT_DIR.glob(f'*{article_id}*.md'))
    
    if md_files:
        content = md_files[0].read_text(encoding='utf-8')
        return jsonify({
            'id': article_id,
            'title': content.split('\n')[0].replace('#', '').strip(),
            'content': content,
            'file': md_files[0].name
        })
    
    return jsonify({'error': 'Article not found'}), 404

@app.route('/api/publish', methods=['POST'])
def api_publish_articles():
    """
    发布选中的文章到 GitHub（支持覆盖发布，带进度跟踪）
    请求体: {"articles": ["article_id1", "article_id2", ...]}
    """
    data = request.get_json() or {}
    article_ids = data.get('articles', [])
    
    if not article_ids:
        return jsonify({'error': 'No articles selected'}), 400
    
    # 初始化发布状态
    with state_lock:
        pipeline_state['publish_status'] = {
            'active': True,
            'total': len(article_ids),
            'processed': 0,
            'current_article': '',
            'results': []
        }
    
    results = []
    search_dirs = [OUTPUT_DIR, OUTPUT_DIR / 'articles', OUTPUT_DIR / 'posts', OUTPUT_DIR / 'raw']
    
    for idx, article_id in enumerate(article_ids):
        # 更新进度
        with state_lock:
            pipeline_state['publish_status']['processed'] = idx
            pipeline_state['publish_status']['current_article'] = article_id
        
        # 查找文章文件
        article_path = None
        for search_dir in search_dirs:
            if search_dir.exists():
                for md_file in search_dir.iterdir():
                    if md_file.suffix == '.md' and md_file.is_file():
                        if md_file.stem == article_id or article_id in md_file.stem:
                            article_path = md_file
                            break
                if article_path:
                    break
        
        if not article_path:
            results.append({
                'id': article_id,
                'success': False,
                'error': 'Article not found'
            })
            continue
        
        try:
            content = article_path.read_text(encoding='utf-8')
            lines = content.split('\n')
            
            # 提取标题
            title = article_path.stem
            for line in lines:
                stripped = line.strip()
                if stripped.startswith('#'):
                    title = stripped.replace('#', '').strip()
                    break
            
            # 提取标签（从 front matter 或内容中）
            tags = []
            in_front_matter = False
            for line in lines:
                if line.strip() == '---':
                    in_front_matter = not in_front_matter
                    continue
                if in_front_matter and line.strip().startswith('tags:'):
                    tag_line = line.split(':', 1)[1].strip()
                    if tag_line.startswith('['):
                        # YAML list format
                        tag_line = tag_line.replace('[', '').replace(']', '')
                        tags = [t.strip() for t in tag_line.split(',') if t.strip()]
                    else:
                        tags = [tag_line]
            
            # 发布到 GitHub（覆盖发布）
            add_log(f'Publishing (override): {title[:30]}...', 'info')
            pub_result = publish_article_to_github(article_path, title, content, tags)
            
            results.append({
                'id': article_id,
                'title': title,
                'success': pub_result.get('success', False),
                'url': pub_result.get('url', ''),
                'error': pub_result.get('error', ''),
                'override': True  # 标记为覆盖发布
            })
            
            if pub_result.get('success'):
                add_log(f'Published (override): {pub_result.get("url", "")}', 'success')
            else:
                add_log(f'Publish failed: {pub_result.get("error", "")}', 'error')
                
        except Exception as e:
            results.append({
                'id': article_id,
                'success': False,
                'error': str(e)
            })
            add_log(f'Publish error: {str(e)}', 'error')
    
    success_count = sum(1 for r in results if r.get('success'))
    
    # 完成发布，更新状态
    with state_lock:
        pipeline_state['publish_status'] = {
            'active': False,
            'total': len(article_ids),
            'processed': len(article_ids),
            'current_article': '',
            'results': results
        }
    
    return jsonify({
        'results': results,
        'total': len(results),
        'success_count': success_count,
        'message': f'Published {success_count}/{len(results)} articles'
    })


@app.route('/api/articles/<article_id>/publish', methods=['POST'])
def api_publish_single_article(article_id):
    """
    发布单篇文章到 GitHub（支持覆盖发布）
    用于预览页面的发布按钮
    """
    search_dirs = [OUTPUT_DIR, OUTPUT_DIR / 'articles', OUTPUT_DIR / 'posts', OUTPUT_DIR / 'raw']
    
    article_path = None
    for search_dir in search_dirs:
        if search_dir.exists():
            for md_file in search_dir.iterdir():
                if md_file.suffix == '.md' and md_file.is_file():
                    if md_file.stem == article_id or article_id in md_file.stem:
                        article_path = md_file
                        break
            if article_path:
                break
    
    if not article_path:
        return jsonify({'success': False, 'error': 'Article not found'}), 404
    
    try:
        content = article_path.read_text(encoding='utf-8')
        lines = content.split('\n')
        
        # 提取标题
        title = article_path.stem
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('#'):
                title = stripped.replace('#', '').strip()
                break
        
        # 提取标签
        tags = []
        in_front_matter = False
        for line in lines:
            if line.strip() == '---':
                in_front_matter = not in_front_matter
                continue
            if in_front_matter and line.strip().startswith('tags:'):
                tag_line = line.split(':', 1)[1].strip()
                if tag_line.startswith('['):
                    tag_line = tag_line.replace('[', '').replace(']', '')
                    tags = [t.strip() for t in tag_line.split(',') if t.strip()]
                else:
                    tags = [tag_line]
        
        # 发布到 GitHub
        add_log(f'Publishing single article: {title[:30]}...', 'info')
        pub_result = publish_article_to_github(article_path, title, content, tags)
        
        if pub_result.get('success'):
            return jsonify({
                'success': True,
                'url': pub_result.get('url', ''),
                'message': 'Article published successfully',
                'override': True
            })
        else:
            return jsonify({
                'success': False,
                'error': pub_result.get('error', 'Unknown error')
            })
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/articles/<article_id>/download')
def api_download_article(article_id):
    """下载文章文件"""
    search_dirs = [OUTPUT_DIR, OUTPUT_DIR / 'articles', OUTPUT_DIR / 'posts', OUTPUT_DIR / 'raw']
    
    for search_dir in search_dirs:
        if search_dir.exists():
            for md_file in search_dir.iterdir():
                if md_file.suffix == '.md' and md_file.is_file():
                    if md_file.stem == article_id or article_id in md_file.stem:
                        return send_from_directory(str(search_dir), md_file.name, as_attachment=True)
    
    return jsonify({'error': 'Article not found'}), 404


@app.route('/api/health')
def api_health():
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'pipeline': get_pipeline() is not None
    })


if __name__ == '__main__':
    OUTPUT_DIR.mkdir(exist_ok=True)
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"Starting Blog Pipeline Dashboard on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)

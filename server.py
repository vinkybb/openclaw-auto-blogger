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
    'log_messages': []
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
            'error': pipeline_state['error']
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
                    
                    processed += 1
                    with state_lock:
                        pipeline_state['articles_processed'] = processed
                        pipeline_state['progress'] = int(processed / len(articles) * 100)
                    
                except Exception as e:
                    add_log(f'Error processing article: {str(e)[:50]}', 'error')
            
            add_log('Pipeline completed!', 'success')
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

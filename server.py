#!/usr/bin/env python3
"""
Blog Pipeline Web Dashboard Server
Flask server providing API and web interface for blog pipeline control
"""

import os
import sys
import json
import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, jsonify, request, send_from_directory

# Add module path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import BlogPipeline

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='static', static_url_path='/static')

# Global state
pipeline_state = {
    'status': 'idle',
    'current_task': None,
    'progress': 0,
    'articles_processed': 0,
    'total_articles': 0,
    'last_run': None,
    'error': None,
    'log_messages': []
}

# Lock for thread-safe operations
state_lock = threading.Lock()

# Pipeline instance
pipeline = None

def get_pipeline():
    """Get or create pipeline instance"""
    global pipeline
    if pipeline is None:
        try:
            pipeline = BlogPipeline('config.yaml')
        except Exception as e:
            logger.error(f"Failed to initialize pipeline: {e}")
            return None
    return pipeline

def add_log(message, level='info'):
    """Add log message to state"""
    with state_lock:
        pipeline_state['log_messages'].append({
            'time': datetime.now().strftime('%H:%M:%S'),
            'message': message,
            'level': level
        })
        # Keep only last 100 messages
        if len(pipeline_state['log_messages']) > 100:
            pipeline_state['log_messages'] = pipeline_state['log_messages'][-100:]

@app.route('/')
def index():
    """Main dashboard page"""
    return render_template('index.html')

@app.route('/preview/<article_id>')
def preview(article_id):
    """Article preview page"""
    return render_template('preview.html', article_id=article_id)

@app.route('/static/<path:filename>')
def static_files(filename):
    """Serve static files"""
    return send_from_directory('static', filename)

@app.route('/output/<path:filename>')
def output_files(filename):
    """Serve output markdown files"""
    return send_from_directory('output', filename)

# ==================== API Routes ====================

@app.route('/api/status')
def api_status():
    """Get pipeline status"""
    with state_lock:
        return jsonify({
            'status': pipeline_state['status'],
            'current_task': pipeline_state['current_task'],
            'progress': pipeline_state['progress'],
            'articles_processed': pipeline_state['articles_processed'],
            'total_articles': pipeline_state['total_articles'],
            'last_run': pipeline_state['last_run'],
            'error': pipeline_state['error']
        })

@app.route('/api/articles')
def api_articles():
    """Get processed articles list"""
    output_dir = Path('output')
    articles = []
    
    if output_dir.exists():
        for md_file in sorted(output_dir.glob('*.md'), reverse=True):
            try:
                content = md_file.read_text(encoding='utf-8')
                # Extract title from first line
                title = content.split('\n')[0].replace('#', '').strip() or md_file.stem
                # Get file stats
                stat = md_file.stat()
                articles.append({
                    'id': md_file.stem,
                    'title': title,
                    'file': md_file.name,
                    'size': stat.st_size,
                    'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M'),
                    'status': 'completed'
                })
            except Exception as e:
                logger.error(f"Error reading {md_file}: {e}")
    
    return jsonify({'articles': articles, 'total': len(articles)})

@app.route('/api/rss-sources')
def api_rss_sources():
    """Get RSS sources configuration"""
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
    """Get recent log messages"""
    with state_lock:
        return jsonify({'logs': pipeline_state['log_messages'][-50:]})

@app.route('/api/pipeline', methods=['POST'])
def api_run_pipeline():
    """Run the full pipeline"""
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
            
            # Fetch articles
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
            
            # Process each article
            processed = 0
            for article in articles:
                try:
                    title = article.get('title', 'Unknown')
                    add_log(f'Processing: {title[:50]}...', 'info')
                    
                    result = p.process_article(article)
                    
                    if result.get('article', {}).get('success'):
                        # Save markdown
                        md_content = result.get('markdown', '')
                        if md_content:
                            filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{title[:30].replace(' ', '_')}.md"
                            output_path = Path('output') / filename
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
    
    # Start pipeline in background thread
    thread = threading.Thread(target=run_pipeline_thread)
    thread.daemon = True
    thread.start()
    
    return jsonify({'status': 'started', 'message': 'Pipeline started in background'})

@app.route('/api/publish', methods=['POST'])
def api_publish():
    """Publish selected articles"""
    data = request.json or {}
    article_ids = data.get('articles', [])
    
    if not article_ids:
        return jsonify({'error': 'No articles selected'}), 400
    
    add_log(f'Publishing {len(article_ids)} articles...', 'info')
    
    try:
        p = get_pipeline()
        if not p:
            raise Exception('Pipeline not initialized')
        
        results = []
        for article_id in article_ids:
            # Find the markdown file
            output_dir = Path('output')
            md_files = list(output_dir.glob(f'*{article_id}*.md'))
            
            if md_files:
                md_file = md_files[0]
                content = md_file.read_text(encoding='utf-8')
                
                # Call publisher
                publish_result = p.publisher.publish(content, md_file.stem)
                results.append({
                    'id': article_id,
                    'success': publish_result.get('success', False),
                    'message': publish_result.get('message', '')
                })
                add_log(f'Published: {md_file.name}', 'success')
            else:
                results.append({
                    'id': article_id,
                    'success': False,
                    'message': 'File not found'
                })
        
        return jsonify({'results': results})
        
    except Exception as e:
        add_log(f'Publish error: {str(e)}', 'error')
        return jsonify({'error': str(e)}), 500

@app.route('/api/expand', methods=['POST'])
def api_expand():
    """Expand a single article"""
    data = request.json or {}
    title = data.get('title', '')
    content = data.get('content', '')
    
    if not title:
        return jsonify({'error': 'Title required'}), 400
    
    add_log(f'Expanding: {title[:50]}...', 'info')
    
    try:
        p = get_pipeline()
        if not p:
            raise Exception('Pipeline not initialized')
        
        # Generate summary first
        summary_result = p.summarizer.summarize(title, content)
        
        if summary_result.get('success'):
            # Then expand
            expand_result = p.expander.expand(
                title=title,
                summary=summary_result.get('summary', ''),
                source_url=data.get('url', ''),
                style='深度分析',
                word_count=2000
            )
            
            if expand_result.get('success'):
                # Save markdown
                md_content = p._format_markdown(
                    title=expand_result.get('title', title),
                    content=expand_result.get('content', ''),
                    tags=expand_result.get('tags', []),
                    source_url=data.get('url', '')
                )
                
                filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{title[:30].replace(' ', '_')}.md"
                output_path = Path('output') / filename
                output_path.write_text(md_content, encoding='utf-8')
                
                add_log(f'Saved expanded article: {filename}', 'success')
                
                return jsonify({
                    'success': True,
                    'title': expand_result.get('title'),
                    'content': expand_result.get('content'),
                    'file': filename
                })
        
        return jsonify({'error': 'Expansion failed'}), 500
        
    except Exception as e:
        add_log(f'Expand error: {str(e)}', 'error')
        return jsonify({'error': str(e)}), 500

@app.route('/api/cancel', methods=['POST'])
def api_cancel():
    """Cancel current pipeline run"""
    with state_lock:
        if pipeline_state['status'] == 'running':
            pipeline_state['status'] = 'cancelled'
            add_log('Pipeline cancelled by user', 'warning')
            return jsonify({'status': 'cancelled'})
        
    return jsonify({'error': 'No running pipeline'}), 400

@app.route('/api/article/<article_id>')
def api_article_detail(article_id):
    """Get article content"""
    output_dir = Path('output')
    md_files = list(output_dir.glob(f'*{article_id}*.md'))
    
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
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'pipeline': get_pipeline() is not None
    })


if __name__ == '__main__':
    # Ensure output directory exists
    Path('output').mkdir(exist_ok=True)
    
    # Start server
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"Starting Blog Pipeline Dashboard on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
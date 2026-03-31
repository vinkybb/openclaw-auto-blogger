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
import re
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, jsonify, request, send_from_directory
from urllib.parse import unquote

# Add module path
BASE_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = BASE_DIR / 'output'  # Files saved to output dir (includes articles subdir)
sys.path.insert(0, str(BASE_DIR))

from app import BlogPipeline

# Article formatter: clean YAML frontmatter and dialogue traces
def format_article(content):
    """Remove YAML frontmatter, dialogue traces, and ensure clean title."""
    # Remove YAML frontmatter (--- ... ---)
    content = re.sub(r'^---\s*\n.*?\n---\s*\n', '', content, flags=re.DOTALL)
    
    # Remove dialogue traces
    dialogue_patterns = [
        r'^我来.*?\n',
        r'^根据摘要.*?\n',
        r'^这篇文章约.*?\n',
        r'^让我先获取原文.*?\n',
        r'^首先.*?\n',
        r'^好的.*?\n',
        r'^下面是.*?\n',
    ]
    for pattern in dialogue_patterns:
        content = re.sub(pattern, '', content, flags=re.MULTILINE)
    
    # Remove leading/trailing whitespace
    content = content.strip()
    
    # Ensure first line is # title
    lines = content.split('\n')
    while lines and not lines[0].strip().startswith('#'):
        lines = lines[1:]
    
    # If no title found, extract from first meaningful content
    if lines and lines[0].strip().startswith('#'):
        # Clean title: remove special chars
        title = lines[0].strip()
        title = re.sub(r'[#"\']+', '', title).strip()
        lines[0] = f"# {title}"
    
    content = '\n'.join(lines)
    return content

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
    return send_from_directory(str(OUTPUT_DIR), filename)

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
    articles = []
    
    # Search in output dir and all subdirs
    search_dirs = [OUTPUT_DIR, OUTPUT_DIR / 'articles', OUTPUT_DIR / 'posts', OUTPUT_DIR / 'raw']
    
    all_md_files = []
    for search_dir in search_dirs:
        if search_dir.exists():
            for md_file in search_dir.iterdir():
                if md_file.suffix == '.md' and md_file.is_file():
                    all_md_files.append(md_file)
    
    # Sort by modification time
    for md_file in sorted(all_md_files, key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            content = md_file.read_text(encoding='utf-8')
            # Extract title: skip status line if present, find first # line
            lines = content.split('\n')
            title = md_file.stem  # default fallback
            status = 'unpublished'
            
            # Check status marker
            for line in lines[:3]:  # Check first 3 lines
                if line.lower().startswith('status: published'):
                    status = 'published'
                elif line.lower().startswith('status: unpublished'):
                    status = 'unpublished'
            
            # Find title (first line starting with #)
            for line in lines:
                stripped = line.strip()
                if stripped.startswith('#'):
                    title = stripped.replace('#', '').strip()
                    break
            
            # Get file stats
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


@app.route('/api/articles/<filename>', methods=['DELETE'])
def api_delete_article(filename):
    """Delete a specific article"""
    # Decode URL-encoded filename
    filename = unquote(filename)
    
    # Search in output dir and all subdirs (same as api_articles)
    search_dirs = [OUTPUT_DIR, OUTPUT_DIR / 'articles', OUTPUT_DIR / 'posts', OUTPUT_DIR / 'raw']
    
    for search_dir in search_dirs:
        article_path = search_dir / filename
        if article_path.exists() and article_path.is_file():
            try:
                article_path.unlink()
                logger.info(f"Deleted article: {filename} from {search_dir.relative_to(OUTPUT_DIR)}")
                return jsonify({'success': True, 'message': f'Deleted {filename}'})
            except Exception as e:
                logger.error(f"Delete failed: {e}")
                return jsonify({'error': str(e)}), 500
    
    return jsonify({'error': 'Article not found'}), 404


@app.route('/api/articles/<filename>/status', methods=['PATCH'])
def api_update_status(filename):
    """Update article status (published/unpublished)"""
    data = request.get_json() or {}
    new_status = data.get('status', 'unpublished')
    
    # Search in all output subdirs
    for subdir in ['articles', 'posts', 'raw']:
        article_path = BASE_DIR / 'output' / subdir / filename
        if article_path.exists() and filename.endswith('.md'):
            try:
                content = article_path.read_text(encoding='utf-8')
                # Toggle status marker at top of file
                if content.startswith('status: published'):
                    content = content.replace('status: published', 'status: unpublished', 1)
                elif content.startswith('status: unpublished'):
                    content = content.replace('status: unpublished', 'status: published', 1)
                else:
                    status_line = f'status: {new_status}\n\n'
                    content = status_line + content
                article_path.write_text(content, encoding='utf-8')
                logger.info(f"Updated status: {filename} -> {new_status}")
                return jsonify({'success': True, 'status': new_status})
            except Exception as e:
                logger.error(f"Status update failed: {e}")
                return jsonify({'error': str(e)}), 500
    
    return jsonify({'error': 'Article not found'}), 404


@app.route('/api/articles/delete-all', methods=['POST'])
def api_delete_all_articles():
    """Delete all articles"""
    articles_dir = OUTPUT_DIR
    
    if not articles_dir.exists():
        return jsonify({'success': True, 'message': 'No articles to delete', 'deleted': 0})
    
    deleted_count = 0
    for f in articles_dir.glob('*.md'):
        try:
            f.unlink()
            deleted_count += 1
        except Exception as e:
            logger.error(f"Failed to delete {f}: {e}")
    
    logger.info(f"Deleted {deleted_count} articles")
    return jsonify({'success': True, 'deleted': deleted_count})


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
                # Check for cancellation
                with state_lock:
                    if pipeline_state['status'] == 'cancelled':
                        add_log('Pipeline stopped by user', 'warning')
                        return
                
                try:
                    title = article.get('title', 'Unknown')
                    add_log(f'Processing: {title[:50]}...', 'info')
                    
                    result = p.process_article(article)
                    
                    if result.get('article', {}).get('success'):
                        # Save markdown
                        md_content = result.get('markdown', '')
                        if md_content:
                            # Format article: remove YAML frontmatter and dialogue traces
                            md_content = format_article(md_content)
                            # Clean title for filename: remove special chars
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
            output_dir = OUTPUT_DIR
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
                output_path = OUTPUT_DIR / filename
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
    output_dir = OUTPUT_DIR
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
    (OUTPUT_DIR).mkdir(exist_ok=True)
    
    # Start server
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"Starting Blog Pipeline Dashboard on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)

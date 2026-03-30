// Blog Pipeline UI Script - Complete Version with Select All & Status Toggle

const elements = {};

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    // Cache DOM elements
    elements.runBtn = document.getElementById('runPipelineBtn');
    elements.stopBtn = document.getElementById('stopPipelineBtn');
    elements.clearBtn = document.getElementById('clearBtn');
    elements.refreshBtn = document.getElementById('refreshBtn');
    elements.statusBar = document.getElementById('statusBar');
    elements.progressDiv = document.getElementById('progressDiv');
    elements.progressFill = document.getElementById('progressFill');
    elements.articlesGrid = document.getElementById('articlesGrid');
    elements.logPanel = document.getElementById('logPanel');
    elements.rssInput = document.getElementById('rssInput');
    elements.topicInput = document.getElementById('topicInput');
    
    // Bind buttons
    if (elements.runBtn) elements.runBtn.addEventListener('click', runPipeline);
    if (elements.stopBtn) elements.stopBtn.addEventListener('click', stopPipeline);
    if (elements.clearBtn) elements.clearBtn.addEventListener('click', clearLogs);
    if (elements.refreshBtn) elements.refreshBtn.addEventListener('click', loadArticles);
    
    // Initial load
    loadArticles();
    startStatusPolling();
});

// Polling for status updates
let statusInterval;
function startStatusPolling() {
    if (statusInterval) clearInterval(statusInterval);
    statusInterval = setInterval(updateStatus, 2000);
}

async function updateStatus() {
    try {
        const res = await fetch('/api/status');
        const data = await res.json();
        updateStatusBar(data);
    } catch (e) {
        console.error('Status poll error:', e);
    }
}

function updateStatusBar(status) {
    if (!elements.statusBar) return;
    
    const statusMap = {
        'idle': {color: '#888', text: '空闲'},
        'running': {color: '#007bff', text: '运行中'},
        'error': {color: '#dc3545', text: '错误'}
    };
    
    const s = statusMap[status.status] || statusMap['idle'];
    elements.statusBar.innerHTML = `
        <span style="color:${s.color};font-weight:bold;">${s.text}</span>
        ${status.current_task ? `<span> | ${status.current_task}</span>` : ''}
        ${status.articles_processed ? `<span> | 已处理: ${status.articles_processed}</span>` : ''}
    `;
    
    // Progress bar
    if (elements.progressDiv && elements.progressFill) {
        const progress = status.progress || 0;
        elements.progressFill.style.width = `${progress}%`;
        elements.progressFill.textContent = `${progress}%`;
        elements.progressDiv.style.display = status.status === 'running' ? 'block' : 'none';
    }
    
    // Update buttons
    if (elements.runBtn) elements.runBtn.disabled = status.status === 'running';
    if (elements.stopBtn) elements.stopBtn.disabled = status.status !== 'running';
}

async function runPipeline() {
    const rss = elements.rssInput?.value || '';
    const topic = elements.topicInput?.value || '';
    
    try {
        const res = await fetch('/api/run', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({rss_url: rss, topic: topic})
        });
        const data = await res.json();
        
        if (data.success) {
            showToast('流水线已启动', 'success');
            addLog('INFO', 'Pipeline started');
        } else {
            showToast('启动失败: ' + data.error, 'error');
        }
    } catch (e) {
        showToast('请求失败: ' + e, 'error');
    }
}

async function stopPipeline() {
    try {
        const res = await fetch('/api/stop', {method: 'POST'});
        const data = await res.json();
        showToast(data.success ? '已停止' : '停止失败', data.success ? 'success' : 'error');
    } catch (e) {
        showToast('请求失败', 'error');
    }
}

async function loadArticles() {
    try {
        const res = await fetch('/api/articles');
        const data = await res.json();
        renderArticles(data.articles || []);
        updateStatusBar({status: 'idle', articles_processed: data.total || 0});
    } catch (e) {
        console.error('Load articles failed:', e);
        if (elements.articlesGrid) {
            elements.articlesGrid.innerHTML = '<div class="error">加载失败，请刷新</div>';
        }
    }
}

function renderArticles(articles) {
    if (!elements.articlesGrid) return;
    
    if (articles.length === 0) {
        elements.articlesGrid.innerHTML = `
            <div class="articles-empty" style="text-align:center;padding:40px;color:var(--text-muted);">
                <div style="font-size:48px;margin-bottom:16px;">📭</div>
                <div style="font-size:16px;">还没有生成的文章</div>
                <div style="font-size:14px;margin-top:8px;">点击"运行流水线"开始处理 RSS</div>
            </div>
        `;
        return;
    }
    
    const published = articles.filter(a => a.status === 'published').length;
    const unpublished = articles.length - published;
    
    elements.articlesGrid.innerHTML = `
        <div class="articles-header" style="display:flex;align-items:center;gap:12px;padding:10px 16px;background:var(--bg-secondary);border-radius:8px;margin-bottom:12px;border:1px solid var(--border-color);">
            <input type="checkbox" id="selectAllCb" style="width:18px;height:18px;cursor:pointer;">
            <label for="selectAllCb" style="font-size:14px;cursor:pointer;user-select:none;">全选</label>
            <span style="font-size:14px;color:var(--text-muted);">(${articles.length} 篇)</span>
            <span style="margin-left:auto;font-size:12px;color:var(--text-muted);">
                已发布 <strong style="color:#228b22;">${published}</strong> | 未发布 <strong style="color:#ff8c00;">${unpublished}</strong>
            </span>
        </div>
        <div class="articles-list">
        ${articles.map(article => `
            <div class="article-card" data-id="${article.id}">
                <input type="checkbox" class="article-select" data-id="${article.id}" style="width:18px;height:18px;cursor:pointer;flex-shrink:0;">
                <span style="font-size:24px;flex-shrink:0;">📝</span>
                <div class="article-info" style="flex:1;min-width:0;overflow:hidden;">
                    <div class="article-title" style="font-size:14px;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${escapeHtml(article.title)}</div>
                    <div style="font-size:12px;color:var(--text-muted);">
                        <span>${article.modified}</span> · <span>${formatSize(article.size)}</span>
                    </div>
                </div>
                <span class="status-badge ${article.status === 'published' ? 'published' : 'unpublished'}" style="font-size:12px;padding:4px 10px;border-radius:12px;flex-shrink:0;">
                    ${article.status === 'published' ? '✓ 已发布' : '○ 未发布'}
                </span>
                <div class="article-actions" style="display:flex;gap:8px;flex-shrink:0;">
                    <button class="btn-icon" onclick="toggleStatus('${escapeHtml(article.file)}')" title="切换状态">${article.status === 'published' ? '📤' : '📥'}</button>
                    <button class="btn-icon" onclick="loadArticleDetail('${article.id}')" title="预览">👁</button>
                    <button class="btn-icon" onclick="downloadArticle('${article.id}')" title="下载">⬇</button>
                    <button class="btn-icon btn-delete" onclick="deleteArticle('${escapeHtml(article.file)}')" title="删除">🗑</button>
                </div>
            </div>
        `).join('')}
        </div>
    `;
    
    // Bind select-all
    const selectAllCb = document.getElementById('selectAllCb');
    if (selectAllCb) {
        selectAllCb.addEventListener('change', (e) => {
            document.querySelectorAll('.article-select').forEach(cb => cb.checked = e.target.checked);
        });
    }
}

function toggleStatus(filename) {
    if (!filename) return;
    fetch(`/api/articles/${encodeURIComponent(filename)}/status`, {
        method: 'PATCH',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({toggle: true})
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            loadArticles();
            showToast('状态已更新', 'success');
        } else {
            showToast('更新失败: ' + (data.error || '未知错误'), 'error');
        }
    })
    .catch(e => showToast('请求失败', 'error'));
}

function deleteArticle(filename) {
    if (!confirm(`确定删除: ${filename}?`)) return;
    fetch(`/api/articles/${encodeURIComponent(filename)}`, {method: 'DELETE'})
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            loadArticles();
            showToast('已删除', 'success');
        } else {
            showToast('删除失败: ' + (data.error || '未知错误'), 'error');
        }
    })
    .catch(e => showToast('请求失败', 'error'));
}

function loadArticleDetail(articleId) {
    fetch(`/api/articles/${articleId}`)
    .then(r => r.json())
    .then(data => {
        if (data.content) {
            // Show in modal or preview panel
            const preview = document.getElementById('articlePreview');
            if (preview) {
                preview.innerHTML = `<pre style="white-space:pre-wrap;padding:16px;background:var(--bg-secondary);border-radius:8px;max-height:400px;overflow:auto;">${escapeHtml(data.content)}</pre>`;
                preview.style.display = 'block';
            }
        }
    })
    .catch(e => showToast('加载失败', 'error'));
}

function downloadArticle(articleId) {
    window.open(`/api/articles/${articleId}/download`, '_blank');
}

function updateSelection() {
    const checked = document.querySelectorAll('.article-select:checked');
    // Could update batch action buttons here
}

function clearLogs() {
    if (elements.logPanel) elements.logPanel.innerHTML = '';
}

function addLog(level, message) {
    if (!elements.logPanel) return;
    const colors = {'INFO': '#007bff', 'WARN': '#ffc107', 'ERROR': '#dc3545'};
    const time = new Date().toLocaleTimeString();
    elements.logPanel.innerHTML += `<div style="color:${colors[level]||'#888'}">[${time}] ${level}: ${message}</div>`;
    elements.logPanel.scrollTop = elements.logPanel.scrollHeight;
}

function showToast(message, type = 'info') {
    const colors = {'success': '#28a745', 'error': '#dc3545', 'info': '#007bff'};
    const toast = document.createElement('div');
    toast.style.cssText = `
        position:fixed;top:20px;right:20px;padding:12px 20px;background:${colors[type]};
        color:#fff;border-radius:8px;font-size:14px;z-index:9999;animation:fadeIn 0.3s;
    `;
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}

function escapeHtml(text) {
    if (!text) return '';
    return text.replace(/[&<>"']/g, m => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    })[m]);
}

function formatSize(bytes) {
    if (!bytes) return '0B';
    const units = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return (bytes / Math.pow(1024, i)).toFixed(1) + units[i];
}
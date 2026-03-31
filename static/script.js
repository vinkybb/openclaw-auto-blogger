// Blog Pipeline UI Script

const elements = {};
let lastLogCount = 0;

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    // Cache DOM elements
    elements.runBtn = document.getElementById('btn-run');
    elements.stopBtn = document.getElementById('btn-cancel');
    elements.refreshBtn = document.getElementById('btn-refresh');
    elements.statusBar = document.getElementById('status-badge');
    elements.progressDiv = document.getElementById('progress-section');
    elements.progressFill = document.getElementById('progress-fill');
    elements.progressPercent = document.getElementById('progress-percent');
    elements.articlesProcessed = document.getElementById('articles-processed');
    elements.totalArticles = document.getElementById('total-articles');
    elements.articlesGrid = document.getElementById('articles-grid');
    elements.logPanel = document.getElementById('log-container');
    elements.sourcesList = document.getElementById('sources-list');
    elements.searchInput = document.getElementById('search-articles');
    elements.publishSelectedBtn = document.getElementById('btn-publish-selected');
    elements.deleteSelectedBtn = document.getElementById('btn-delete-selected');
    elements.selectAllCb = document.getElementById('selectAllCb');
    elements.statSources = document.getElementById('stat-sources');
    elements.statArticles = document.getElementById('stat-articles');
    elements.statLastRun = document.getElementById('stat-last-run');
    elements.articlesCount = document.getElementById('articles-count');
    
    // Bind buttons
    if (elements.runBtn) elements.runBtn.addEventListener('click', runPipeline);
    if (elements.stopBtn) elements.stopBtn.addEventListener('click', stopPipeline);
    if (elements.refreshBtn) elements.refreshBtn.addEventListener('click', loadArticles);
    if (elements.searchInput) elements.searchInput.addEventListener('input', filterArticles);
    if (elements.publishSelectedBtn) elements.publishSelectedBtn.addEventListener('click', publishSelected);
    if (elements.deleteSelectedBtn) elements.deleteSelectedBtn.addEventListener('click', deleteSelected);
    if (elements.selectAllCb) elements.selectAllCb.addEventListener('change', (e) => {
        document.querySelectorAll('.article-select').forEach(cb => cb.checked = e.target.checked);
        updateSelection();
    });
    
    // Initial load
    loadArticles();
    loadSources();
    startStatusPolling();
});

// Polling for status and logs
let statusInterval;
let logInterval;

function startStatusPolling() {
    if (statusInterval) clearInterval(statusInterval);
    statusInterval = setInterval(updateStatus, 2000);
    updateStatus();
    
    // Also poll logs
    if (logInterval) clearInterval(logInterval);
    logInterval = setInterval(loadLogs, 1000);
    loadLogs();
}

async function loadLogs() {
    try {
        const res = await fetch('/api/logs');
        const data = await res.json();
        const logs = data.logs || [];
        
        // 日志数量变化时刷新（增加或减少都刷新，减少表示流水线重新启动）
        if (logs.length !== lastLogCount) {
            renderLogs(logs);
            lastLogCount = logs.length;
        }
    } catch (e) {
        console.error('Load logs error:', e);
    }
}

function renderLogs(logs) {
    if (!elements.logPanel) return;
    
    // Remove empty state message
    const emptyMsg = elements.logPanel.querySelector('.log-empty');
    if (emptyMsg) emptyMsg.remove();
    
    const colors = {'info': '#007bff', 'warning': '#ffc107', 'error': '#dc3545', 'success': '#28a745'};
    
    // Clear and re-render all logs
    elements.logPanel.innerHTML = logs.map(log => {
        const color = colors[log.level] || '#888';
        return `<div style="color:${color};"><span style="opacity:0.6">[${log.time}]</span> <strong>${log.level.toUpperCase()}</strong>: ${escapeHtml(log.message)}</div>`;
    }).join('');
    
    elements.logPanel.scrollTop = elements.logPanel.scrollHeight;
}

async function updateStatus() {
    try {
        const res = await fetch('/api/status');
        const data = await res.json();
        updateStatusBar(data);
    } catch (e) {
        console.error('Status poll error:', e);
        if (elements.statusBar) {
            elements.statusBar.innerHTML = '<span class="status-dot" style="background:#dc3545;"></span><span class="status-text">连接失败</span>';
        }
    }
}

function updateStatusBar(status) {
    if (!elements.statusBar) return;
    
    const statusMap = {
        'idle': {color: '#28a745', text: '空闲', dotClass: 'idle'},
        'running': {color: '#007bff', text: '运行中', dotClass: 'running'},
        'error': {color: '#dc3545', text: '错误', dotClass: 'error'},
        'cancelled': {color: '#ffc107', text: '已取消', dotClass: 'idle'}
    };
    
    const s = statusMap[status.status] || statusMap['idle'];
    elements.statusBar.innerHTML = `
        <span class="status-dot ${s.dotClass}" style="background:${s.color};"></span>
        <span class="status-text">${s.text}</span>
    `;
    
    // Progress bar
    if (elements.progressDiv) {
        const progress = status.progress || 0;
        if (status.status === 'running') {
            elements.progressDiv.style.display = 'block';
            if (elements.progressFill) elements.progressFill.style.width = `${progress}%`;
            if (elements.progressPercent) elements.progressPercent.textContent = `${progress}%`;
            if (elements.articlesProcessed) elements.articlesProcessed.textContent = status.articles_processed || 0;
            if (elements.totalArticles) elements.totalArticles.textContent = status.total_articles || 0;
        } else {
            elements.progressDiv.style.display = 'none';
        }
    }
    
    // Update buttons
    if (elements.runBtn) elements.runBtn.style.display = status.status === 'running' ? 'none' : 'inline-flex';
    if (elements.stopBtn) elements.stopBtn.style.display = status.status === 'running' ? 'inline-flex' : 'none';
    
    // Update last run
    if (elements.statLastRun && status.last_run) {
        elements.statLastRun.textContent = formatTime(status.last_run);
    }
    
    // Reload articles when pipeline completes
    if (status.status === 'idle' && status.progress === 100) {
        loadArticles();
    }
}

async function runPipeline() {
    if (!elements.runBtn) return;
    elements.runBtn.disabled = true;
    elements.runBtn.textContent = '⏳ 启动中...';
    
    try {
        const res = await fetch('/api/pipeline', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'}
        });
        const data = await res.json();
        
        if (res.ok) {
            // 重置日志计数器，确保新日志能正确加载
            lastLogCount = 0;
            // 清空当前日志显示
            if (elements.logPanel) {
                elements.logPanel.innerHTML = '';
            }
            showToast('流水线已启动', 'success');
        } else {
            showToast('启动失败: ' + (data.error || '未知错误'), 'error');
        }
    } catch (e) {
        showToast('请求失败: ' + e, 'error');
    } finally {
        elements.runBtn.disabled = false;
        elements.runBtn.textContent = '⚡ 运行流水线';
    }
}

async function stopPipeline() {
    try {
        const res = await fetch('/api/cancel', {method: 'POST'});
        const data = await res.json();
        showToast(data.status === 'cancelled' ? '已停止' : '停止失败', data.status === 'cancelled' ? 'success' : 'error');
    } catch (e) {
        showToast('请求失败', 'error');
    }
}

async function loadArticles() {
    try {
        const res = await fetch('/api/articles');
        const data = await res.json();
        renderArticles(data.articles || []);
        
        if (elements.statArticles) {
            elements.statArticles.textContent = data.total || 0;
        }
    } catch (e) {
        console.error('Load articles failed:', e);
        if (elements.articlesGrid) {
            elements.articlesGrid.innerHTML = '<div class="error" style="text-align:center;padding:40px;color:#dc3545;">加载失败，请刷新页面</div>';
        }
    }
}

async function loadSources() {
    try {
        const res = await fetch('/api/rss-sources');
        const data = await res.json();
        renderSources(data.sources || []);
        
        if (elements.statSources) {
            elements.statSources.textContent = data.total || 0;
        }
    } catch (e) {
        console.error('Load sources failed:', e);
    }
}

function renderSources(sources) {
    if (!elements.sourcesList) return;
    
    if (sources.length === 0) {
        elements.sourcesList.innerHTML = `
            <div class="source-empty" style="text-align:center;padding:20px;color:var(--text-muted);">
                <div>暂无 RSS 源配置</div>
                <div style="font-size:12px;margin-top:8px;">请编辑 config.yaml 添加源</div>
            </div>
        `;
        return;
    }
    
    elements.sourcesList.innerHTML = sources.map(source => `
        <div class="source-item">
            <span class="source-icon">${source.type === 'rss' ? '📡' : '🌐'}</span>
            <div class="source-info">
                <div class="source-name">${escapeHtml(source.name)}</div>
                <div class="source-url">${escapeHtml(source.url)}</div>
            </div>
            <span class="source-status ${source.enabled ? 'enabled' : 'disabled'}">
                ${source.enabled ? '✓' : '✗'}
            </span>
        </div>
    `).join('');
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
    
    if (elements.articlesCount) {
        elements.articlesCount.textContent = `(${articles.length} 篇) | 已发布 ${published} | 未发布 ${unpublished}`;
    }
    
    elements.articlesGrid.innerHTML = articles.map(article => `
        <div class="article-card" data-id="${article.id}" data-file="${encodeURIComponent(article.file)}" data-title="${escapeHtml(article.title).toLowerCase()}">
            <input type="checkbox" class="article-select" data-id="${article.id}">
            <span class="article-icon">📝</span>
            <div class="article-info">
                <div class="article-title" style="font-size:14px;font-weight:500;color:#e6edf3;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:block;margin-bottom:4px;" title="${escapeHtml(article.title)}">${escapeHtml(article.title)}</div>
                <div class="article-meta">
                    <span>${article.modified}</span>
                    <span>${formatSize(article.size)}</span>
                </div>
            </div>
            <span class="article-status status-${article.status === 'published' ? 'published' : 'unpublished'}">
                ${article.status === 'published' ? '✓ 已发布' : '○ 未发布'}
            </span>
            <div class="article-actions">
                <button class="btn-icon" onclick="previewArticle('${article.id}')" title="预览">👁</button>
                <button class="btn-icon" onclick="downloadArticle('${article.id}')" title="下载">⬇</button>
                <button class="btn-icon btn-delete" onclick="deleteArticle('${encodeURIComponent(article.file)}')" title="删除">🗑</button>
            </div>
        </div>
    `).join('');
    
    document.querySelectorAll('.article-select').forEach(cb => {
        cb.addEventListener('change', updateSelection);
    });
    
    if (elements.selectAllCb) {
        elements.selectAllCb.checked = false;
    }
    
    // 重置选择状态，确保按钮状态正确
    updateSelection();
}

function filterArticles() {
    const query = elements.searchInput?.value?.toLowerCase() || '';
    const cards = document.querySelectorAll('.article-card');
    
    cards.forEach(card => {
        const title = card.dataset.title || '';
        card.style.display = title.includes(query) ? 'flex' : 'none';
    });
}

function updateSelection() {
    const checked = document.querySelectorAll('.article-select:checked');
    const total = document.querySelectorAll('.article-select');
    
    if (elements.publishSelectedBtn) {
        elements.publishSelectedBtn.disabled = checked.length === 0;
        elements.publishSelectedBtn.textContent = checked.length > 0 ? `📤 发布选中 (${checked.length})` : '📤 发布选中';
    }
    
    if (elements.deleteSelectedBtn) {
        elements.deleteSelectedBtn.style.display = checked.length > 0 ? 'inline-flex' : 'none';
        elements.deleteSelectedBtn.textContent = checked.length > 0 ? `🗑 删除选中 (${checked.length})` : '🗑 删除选中';
    }
    
    if (elements.selectAllCb) {
        if (checked.length === 0) {
            elements.selectAllCb.checked = false;
            elements.selectAllCb.indeterminate = false;
        } else if (checked.length === total.length) {
            elements.selectAllCb.checked = true;
            elements.selectAllCb.indeterminate = false;
        } else {
            elements.selectAllCb.checked = false;
            elements.selectAllCb.indeterminate = true;
        }
    }
}

async function deleteSelected() {
    const checked = document.querySelectorAll('.article-select:checked');
    if (checked.length === 0) return;
    
    if (!confirm(`确定删除选中的 ${checked.length} 篇文章？此操作不可恢复。`)) return;
    
    const files = Array.from(checked).map(cb => {
        const card = cb.closest('.article-card');
        return card ? card.dataset.file : null;
    }).filter(file => file);
    
    let successCount = 0;
    let failCount = 0;
    
    for (const file of files) {
        try {
            const res = await fetch(`/api/articles/${file}`, {method: 'DELETE'});
            const data = await res.json();
            if (data.success) {
                successCount++;
            } else {
                failCount++;
            }
        } catch (e) {
            failCount++;
        }
    }
    
    if (successCount > 0) {
        showToast(`已删除 ${successCount} 篇文章`, 'success');
    }
    if (failCount > 0) {
        showToast(`${failCount} 篇文章删除失败`, 'error');
    }
    
    loadArticles();
}

async function publishSelected() {
    const checked = document.querySelectorAll('.article-select:checked');
    if (checked.length === 0) return;
    
    const ids = Array.from(checked).map(cb => cb.dataset.id);
    
    try {
        const res = await fetch('/api/publish', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({articles: ids})
        });
        const data = await res.json();
        
        if (data.results) {
            const success = data.results.filter(r => r.success).length;
            showToast(`已发布 ${success}/${ids.length} 篇文章`, success > 0 ? 'success' : 'error');
            loadArticles();
        }
    } catch (e) {
        showToast('发布失败: ' + e, 'error');
    }
}

function deleteArticle(filename) {
    if (!filename) return;
    if (!confirm('确定删除这篇文章？')) return;
    
    fetch(`/api/articles/${filename}`, {method: 'DELETE'})
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

function previewArticle(articleId) {
    window.open(`/preview/${articleId}`, '_blank');
}

function downloadArticle(articleId) {
    window.open(`/api/articles/${articleId}/download`, '_blank');
}

function showToast(message, type = 'info') {
    const colors = {'success': '#28a745', 'error': '#dc3545', 'info': '#007bff', 'warning': '#ffc107'};
    const toast = document.createElement('div');
    toast.style.cssText = `
        position:fixed;top:20px;right:20px;padding:12px 20px;background:${colors[type] || colors.info};
        color:#fff;border-radius:8px;font-size:14px;z-index:9999;animation:fadeIn 0.3s;
        box-shadow:0 4px 12px rgba(0,0,0,0.15);
    `;
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transition = 'opacity 0.3s';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

function escapeHtml(text) {
    if (!text) return '';
    return text
        .replace(/&/g, '\x26amp;')
        .replace(/</g, '\x26lt;')
        .replace(/>/g, '\x26gt;')
        .replace(/"/g, '\x26quot;')
        .replace(/'/g, '\x26#39;');
}

function formatSize(bytes) {
    if (!bytes) return '0B';
    const units = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return (bytes / Math.pow(1024, i)).toFixed(1) + units[i];
}

function formatTime(isoString) {
    if (!isoString) return '-';
    try {
        const d = new Date(isoString);
        return d.toLocaleString('zh-CN', {month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit'});
    } catch (e) {
        return '-';
    }
}

// Add CSS animation
const style = document.createElement('style');
style.textContent = `
    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(-10px); }
        to { opacity: 1; transform: translateY(0); }
    }
    .btn-icon {
        background: none;
        border: none;
        cursor: pointer;
        font-size: 16px;
        padding: 4px 8px;
        border-radius: 4px;
        transition: background 0.2s;
    }
    .btn-icon:hover {
        background: var(--bg-secondary);
    }
    .btn-delete:hover {
        background: #fee;
    }
    .article-card {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 12px 16px;
        background: var(--bg-secondary);
        border: 1px solid var(--border-color);
        border-radius: 8px;
        transition: box-shadow 0.2s;
    }
    .article-info {
        flex: 1;
        min-width: 0;
        overflow: hidden;
    }
    .article-title {
        font-size: 14px;
        font-weight: 500;
        color: #e6edf3;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        display: block;
        margin-bottom: 4px;
    }
    .article-card:hover {
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    }
    .status-badge.published {
        background: #d4edda;
        color: #155724;
    }
    .status-badge.unpublished {
        background: #fff3cd;
        color: #856404;
    }
    .source-item {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 10px 12px;
        background: var(--bg-primary);
        border: 1px solid var(--border-color);
        border-radius: 6px;
        margin-bottom: 6px;
    }
    .source-info {
        flex: 1;
        min-width: 0;
    }
    .source-name {
        font-weight: 500;
        font-size: 14px;
    }
    .source-url {
        font-size: 12px;
        color: var(--text-muted);
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }
    .source-status.enabled {
        color: #28a745;
    }
    .source-status.disabled {
        color: #dc3545;
    }
`;
document.head.appendChild(style);

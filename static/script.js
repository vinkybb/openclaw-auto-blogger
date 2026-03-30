/**
 * Blog Pipeline Dashboard - Frontend Logic
 */

// State
const state = {
    status: 'idle',
    selectedArticles: [],
    logs: [],
    pollInterval: null
};

// DOM Elements
const elements = {
    statusBadge: document.getElementById('status-badge'),
    statusDot: document.querySelector('.status-dot'),
    statusText: document.querySelector('.status-text'),
    btnRun: document.getElementById('btn-run'),
    btnCancel: document.getElementById('btn-cancel'),
    progressSection: document.getElementById('progress-section'),
    progressFill: document.getElementById('progress-fill'),
    progressPercent: document.getElementById('progress-percent'),
    articlesProcessed: document.getElementById('articles-processed'),
    totalArticles: document.getElementById('total-articles'),
    statSources: document.getElementById('stat-sources'),
    statArticles: document.getElementById('stat-articles'),
    statLastRun: document.getElementById('stat-last-run'),
    sourcesList: document.getElementById('sources-list'),
    logContainer: document.getElementById('log-container'),
    articlesGrid: document.getElementById('articles-grid'),
    searchArticles: document.getElementById('search-articles'),
    btnRefresh: document.getElementById('btn-refresh'),
    btnPublishSelected: document.getElementById('btn-publish-selected'),
    modal: document.getElementById('article-modal'),
    modalTitle: document.getElementById('modal-title'),
    modalContent: document.getElementById('modal-content'),
    modalClose: document.getElementById('modal-close'),
    btnCloseModal: document.getElementById('btn-close-modal'),
    btnPublishModal: document.getElementById('btn-publish-modal'),
    serverStatus: document.getElementById('server-status')
};

// ==================== API Functions ====================

async function fetchAPI(endpoint, options = {}) {
    try {
        const response = await fetch(`/api/${endpoint}`, {
            ...options,
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            }
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        return await response.json();
    } catch (error) {
        console.error(`API Error (${endpoint}):`, error);
        return null;
    }
}

async function loadStatus() {
    const data = await fetchAPI('status');
    if (data) {
        updateStatus(data);
    }
}

async function loadSources() {
    const data = await fetchAPI('rss-sources');
    if (data) {
        renderSources(data.sources);
        elements.statSources.textContent = data.total;
    }
}

async function loadArticles() {
    const data = await fetchAPI('articles');
    if (data) {
        renderArticles(data.articles);
        elements.statArticles.textContent = data.total;
    }
}

async function loadLogs() {
    const data = await fetchAPI('logs');
    if (data) {
        renderLogs(data.logs);
    }
}

async function runPipeline() {
    const data = await fetchAPI('pipeline', { method: 'POST' });
    if (data) {
        showToast('Pipeline started!', 'success');
        startPolling();
    } else {
        showToast('Failed to start pipeline', 'error');
    }
}

async function cancelPipeline() {
    const data = await fetchAPI('cancel', { method: 'POST' });
    if (data) {
        showToast('Pipeline cancelled', 'warning');
        stopPolling();
    }
}

async function publishArticles(articleIds) {
    const data = await fetchAPI('publish', {
        method: 'POST',
        body: JSON.stringify({ articles: articleIds })
    });
    
    if (data) {
        const success = data.results.filter(r => r.success).length;
        showToast(`Published ${success} articles`, 'success');
    } else {
        showToast('Publish failed', 'error');
    }
}

async function loadArticleDetail(articleId) {
    const data = await fetchAPI(`article/${articleId}`);
    if (data) {
        showModal(data);
    }
}

// ==================== UI Functions ====================

function updateStatus(data) {
    state.status = data.status;
    
    // Update badge
    elements.statusBadge.className = `status-badge status-${data.status}`;
    elements.statusText.textContent = 
        data.status === 'running' ? 'Running' :
        data.status === 'error' ? 'Error' :
        data.status === 'cancelled' ? 'Cancelled' :
        'Idle';
    
    // Update buttons
    if (data.status === 'running') {
        elements.btnRun.style.display = 'none';
        elements.btnCancel.style.display = 'inline-flex';
        elements.progressSection.style.display = 'block';
    } else {
        elements.btnRun.style.display = 'inline-flex';
        elements.btnCancel.style.display = 'none';
        if (data.progress === 100) {
            setTimeout(() => {
                elements.progressSection.style.display = 'none';
            }, 2000);
        }
    }
    
    // Update progress
    elements.progressFill.style.width = `${data.progress}%`;
    elements.progressPercent.textContent = `${data.progress}%`;
    elements.articlesProcessed.textContent = data.articles_processed;
    elements.totalArticles.textContent = data.total_articles;
    
    // Update last run
    if (data.last_run) {
        const date = new Date(data.last_run);
        elements.statLastRun.textContent = date.toLocaleString('zh-CN', {
            hour: '2-digit',
            minute: '2-digit'
        });
    }
}

function renderSources(sources) {
    elements.sourcesList.innerHTML = sources.map(source => `
        <div class="source-item ${source.enabled ? '' : 'disabled'}">
            <div class="source-icon">${source.type === 'rss' ? '📡' : '🌐'}</div>
            <div class="source-info">
                <div class="source-name">${source.name}</div>
                <div class="source-url">${source.url}</div>
            </div>
            <div class="source-category">${source.category}</div>
            <div class="source-toggle">
                <input type="checkbox" ${source.enabled ? 'checked' : ''} disabled>
            </div>
        </div>
    `).join('');
}

function renderArticles(articles) {
    if (articles.length === 0) {
        elements.articlesGrid.innerHTML = `
            <div class="articles-empty">
                <div class="empty-icon">📭</div>
                <div class="empty-text">还没有生成的文章</div>
                <div class="empty-hint">点击"运行流水线"开始处理 RSS</div>
            </div>
        `;
        return;
    }
    
    elements.articlesGrid.innerHTML = articles.map(article => `
        <div class="article-card" data-id="${article.id}">
            <input type="checkbox" class="article-select" data-id="${article.id}">
            <div class="article-icon">📝</div>
            <div class="article-info">
                <div class="article-title">${escapeHtml(article.title)}</div>
                <div class="article-meta">
                    <span>${article.modified}</span>
                    <span>${formatSize(article.size)}</span>
                </div>
            </div>
            <div class="article-actions">
                <button class="btn-icon" onclick="loadArticleDetail('${article.id}')" title="预览">
                    👁
                </button>
                <button class="btn-icon" onclick="downloadArticle('${article.id}')" title="下载">
                    ⬇
                </button>
            </div>
        </div>
    `).join('');
    
    // Bind selection events
    document.querySelectorAll('.article-select').forEach(cb => {
        cb.addEventListener('change', updateSelection);
    });
}

function renderLogs(logs) {
    if (logs.length === 0) {
        elements.logContainer.innerHTML = `
            <div class="log-empty">点击"运行流水线"开始处理...</div>
        `;
        return;
    }
    
    // Only show new logs
    const newLogs = logs.slice(-10);
    newLogs.forEach(log => {
        if (!state.logs.some(l => l.time === log.time && l.message === log.message)) {
            state.logs.push(log);
            appendLog(log);
        }
    });
    
    // Keep only last 100
    if (state.logs.length > 100) {
        state.logs = state.logs.slice(-100);
    }
}

function appendLog(log) {
    if (elements.logContainer.querySelector('.log-empty')) {
        elements.logContainer.innerHTML = '';
    }
    
    const logEl = document.createElement('div');
    logEl.className = `log-item log-${log.level}`;
    logEl.innerHTML = `
        <span class="log-time">${log.time}</span>
        <span class="log-message">${escapeHtml(log.message)}</span>
    `;
    elements.logContainer.appendChild(logEl);
    
    // Auto scroll
    elements.logContainer.scrollTop = elements.logContainer.scrollHeight;
}

function updateSelection() {
    const checkboxes = document.querySelectorAll('.article-select:checked');
    state.selectedArticles = Array.from(checkboxes).map(cb => cb.dataset.id);
    
    elements.btnPublishSelected.disabled = state.selectedArticles.length === 0;
    elements.btnPublishSelected.textContent = 
        state.selectedArticles.length > 0 
            ? `📤 发布选中 (${state.selectedArticles.length})`
            : '📤 发布选中';
}

function showModal(article) {
    elements.modalTitle.textContent = article.title;
    elements.modalContent.textContent = article.content;
    elements.modal.classList.add('active');
    elements.modal.dataset.id = article.id;
}

function hideModal() {
    elements.modal.classList.remove('active');
}

function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.classList.add('fade-out');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// ==================== Helpers ====================

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatSize(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function downloadArticle(articleId) {
    const link = document.createElement('a');
    link.href = `/output/${articleId}.md`;
    link.download = `${articleId}.md`;
    link.click();
}

// ==================== Polling ====================

function startPolling() {
    if (state.pollInterval) return;
    
    state.pollInterval = setInterval(async () => {
        await loadStatus();
        await loadLogs();
        
        if (state.status !== 'running') {
            stopPolling();
            await loadArticles();
        }
    }, 1000);
}

function stopPolling() {
    if (state.pollInterval) {
        clearInterval(state.pollInterval);
        state.pollInterval = null;
    }
}

// ==================== Event Bindings ====================

elements.btnRun.addEventListener('click', () => {
    if (state.status !== 'running') {
        state.logs = [];
        elements.logContainer.innerHTML = '';
        runPipeline();
    }
});

elements.btnCancel.addEventListener('click', cancelPipeline);

elements.btnRefresh.addEventListener('click', () => {
    loadArticles();
    showToast('Articles refreshed', 'info');
});

elements.btnPublishSelected.addEventListener('click', () => {
    if (state.selectedArticles.length > 0) {
        publishArticles(state.selectedArticles);
    }
});

elements.modalClose.addEventListener('click', hideModal);
elements.btnCloseModal.addEventListener('click', hideModal);
elements.btnPublishModal.addEventListener('click', () => {
    const articleId = elements.modal.dataset.id;
    if (articleId) {
        publishArticles([articleId]);
        hideModal();
    }
});

elements.searchArticles.addEventListener('input', (e) => {
    const query = e.target.value.toLowerCase();
    document.querySelectorAll('.article-card').forEach(card => {
        const title = card.querySelector('.article-title').textContent.toLowerCase();
        card.style.display = title.includes(query) ? '' : 'none';
    });
});

// Close modal on outside click
elements.modal.addEventListener('click', (e) => {
    if (e.target === elements.modal) {
        hideModal();
    }
});

// ==================== Initialization ====================

async function init() {
    await loadStatus();
    await loadSources();
    await loadArticles();
    
    // If running, start polling
    if (state.status === 'running') {
        startPolling();
    }
    
    // Periodic health check
    setInterval(async () => {
        const health = await fetchAPI('health');
        elements.serverStatus.innerHTML = health 
            ? '✅ Server OK'
            : '❌ Server Error';
    }, 30000);
}

// Start
init();
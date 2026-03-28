// ============================================
// Blog Pipeline - Modern UI Controller
// ============================================

// 状态管理
const state = {
    sources: [],
    selectedSources: new Set(),
    articles: [],
    isRunning: false,
    currentStage: 0
};

// 阶段定义
const STAGES = [
    { id: 'fetch', label: '获取内容', icon: '📥' },
    { id: 'expand', label: '话题扩展', icon: '🔄' },
    { id: 'summarize', label: '生成摘要', icon: '✨' },
    { id: 'image', label: '配图生成', icon: '🎨' },
    { id: 'publish', label: '发布文章', icon: '🚀' }
];

// API 基础路径
const API_BASE = '';

// ============================================
// 工具函数
// ============================================

function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    
    const icons = {
        success: '<svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
        error: '<svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
        info: '<svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>',
        warning: '<svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>'
    };
    
    toast.innerHTML = `${icons[type]}<span class="toast-message">${message}</span>`;
    container.appendChild(toast);
    
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(10px)';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

function formatTime(date) {
    const d = new Date(date);
    return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function updateStatus(text, isActive = false) {
    const statusText = document.querySelector('.status-text');
    const statusDot = document.querySelector('.status-dot');
    if (statusText) statusText.textContent = text;
    if (statusDot) {
        statusDot.style.background = isActive ? 'var(--warning)' : 'var(--success)';
    }
}

// ============================================
// RSS 源管理
// ============================================

async function loadRssSources() {
    const grid = document.getElementById('rssGrid');
    grid.innerHTML = '<div class="skeleton-loader"><div class="skeleton-item"></div><div class="skeleton-item"></div><div class="skeleton-item"></div><div class="skeleton-item"></div></div>';
    
    try {
        const response = await fetch(`${API_BASE}/api/rss-sources`);
        const data = await response.json();
        
        state.sources = data.sources || [];
        state.selectedSources = new Set();
        
        renderSources();
        updateSourceCount();
    } catch (error) {
        console.error('加载RSS源失败:', error);
        grid.innerHTML = `<div class="empty-state"><p class="empty-desc">加载失败，请重试</p></div>`;
        showToast('加载RSS源失败', 'error');
    }
}

function renderSources() {
    const grid = document.getElementById('rssGrid');
    
    if (state.sources.length === 0) {
        grid.innerHTML = `<div class="empty-state"><p class="empty-desc">暂无RSS源</p></div>`;
        return;
    }
    
    grid.innerHTML = state.sources.map((source, index) => `
        <div class="source-card" onclick="toggleSource(${index})" data-index="${index}">
            <input type="checkbox" id="source-${index}" ${state.selectedSources.has(index) ? 'checked' : ''}>
            <div class="source-checkbox">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                    <polyline points="20 6 9 17 4 12"/>
                </svg>
            </div>
            <div class="source-info">
                <div class="source-name">${escapeHtml(source.name || source)}</div>
                <div class="source-meta">${source.url ? new URL(source.url).hostname : 'RSS源'}</div>
            </div>
        </div>
    `).join('');
}

function toggleSource(index) {
    const card = document.querySelector(`[data-index="${index}"]`);
    if (state.selectedSources.has(index)) {
        state.selectedSources.delete(index);
        card.classList.remove('selected');
    } else {
        state.selectedSources.add(index);
        card.classList.add('selected');
    }
    updateSourceCount();
}

function toggleAllRss(selectAll) {
    state.sources.forEach((_, index) => {
        const card = document.querySelector(`[data-index="${index}"]`);
        if (selectAll) {
            state.selectedSources.add(index);
            card.classList.add('selected');
        } else {
            state.selectedSources.delete(index);
            card.classList.remove('selected');
        }
    });
    updateSourceCount();
}

function updateSourceCount() {
    document.getElementById('sourceCount').textContent = `${state.selectedSources.size} 个源已选`;
}

// ============================================
// 文章数量控制
// ============================================

function adjustCount(delta) {
    const input = document.getElementById('articleCount');
    let value = parseInt(input.value) || 3;
    value = Math.max(1, Math.min(10, value + delta));
    input.value = value;
}

// ============================================
// 流水线控制
// ============================================

async function startPipeline() {
    if (state.isRunning) {
        showToast('流水线正在运行中', 'warning');
        return;
    }
    
    const selectedSources = Array.from(state.selectedSources).map(i => state.sources[i]);
    if (selectedSources.length === 0) {
        showToast('请至少选择一个RSS源', 'warning');
        return;
    }
    
    const customTopic = document.getElementById('customTopic').value.trim();
    const articleCount = parseInt(document.getElementById('articleCount').value) || 3;
    
    state.isRunning = true;
    updateStatus('运行中...', true);
    
    // 显示进度区域
    const progressSection = document.getElementById('progressSection');
    progressSection.style.display = 'block';
    initStageIndicator();
    
    // 禁用启动按钮
    const startBtn = document.getElementById('startBtn');
    startBtn.disabled = true;
    startBtn.innerHTML = `<svg class="animate-spin" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10" opacity="0.3"/><path d="M12 2a10 10 0 0110 10"/></svg><span>运行中...</span>`;
    
    try {
        const response = await fetch(`${API_BASE}/api/pipeline`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                sources: selectedSources,
                topics: customTopic ? [customTopic] : []
            })
        });
        
        const result = await response.json();
        
        if (result.status === 'success' || result.status === 'started') {
            showToast('流水线启动成功', 'success');
            pollPipelineStatus();
        } else {
            throw new Error(result.message || '启动失败');
        }
    } catch (error) {
        console.error('启动流水线失败:', error);
        showToast(`启动失败: ${error.message}`, 'error');
        resetPipelineState();
    }
}

function initStageIndicator() {
    const stageIndicator = document.getElementById('stageIndicator');
    stageIndicator.innerHTML = `<div class="stage-line"></div>` + STAGES.map((stage, index) => `
        <div class="stage-item" id="stage-${stage.id}">
            <div class="stage-icon">${index + 1}</div>
            <div class="stage-label">${stage.label}</div>
        </div>
    `).join('');
    
    // 清空日志
    document.getElementById('logContainer').innerHTML = '';
}

function updateStage(stageId, status) {
    const stageElement = document.getElementById(`stage-${stageId}`);
    if (!stageElement) return;
    
    stageElement.classList.remove('active', 'completed');
    if (status === 'active') stageElement.classList.add('active');
    if (status === 'completed') stageElement.classList.add('completed');
}

function addLog(message, type = 'info') {
    const logContainer = document.getElementById('logContainer');
    const entry = document.createElement('div');
    entry.className = `log-entry ${type}`;
    entry.innerHTML = `
        <span class="log-time">${formatTime(new Date())}</span>
        <span class="log-message">${escapeHtml(message)}</span>
    `;
    logContainer.appendChild(entry);
    logContainer.scrollTop = logContainer.scrollHeight;
}

async function pollPipelineStatus() {
    // 模拟进度更新（实际应用中应该从服务器获取状态）
    const stages = ['fetch', 'expand', 'summarize', 'image', 'publish'];
    let lastLogIndex = 0; // 记录上次看到的日志位置
    
    const poll = async () => {
        if (!state.isRunning) return;
        
        try {
            const response = await fetch(`${API_BASE}/api/status`);
            const data = await response.json();
            
            // 更新阶段
            if (data.current_stage) {
                stages.forEach((stage, index) => {
                    if (index < stages.indexOf(data.current_stage)) {
                        updateStage(stage, 'completed');
                    } else if (stage === data.current_stage) {
                        updateStage(stage, 'active');
                    }
                });
            }
            
            // 添加所有新日志（从上次位置开始）
            if (data.logs && data.logs.length > 0) {
                for (let i = lastLogIndex; i < data.logs.length; i++) {
                    const log = data.logs[i];
                    addLog(log.msg || log.message, log.type || 'info');
                }
                lastLogIndex = data.logs.length;
            }
            
            if (data.status === 'completed') {
                showToast('流水线执行完成', 'success');
                resetPipelineState();
                loadArticles();
            } else if (data.status === 'error') {
                showToast(`执行失败: ${data.error}`, 'error');
                resetPipelineState();
            } else {
                setTimeout(poll, 1000); // 缩短轮询间隔到1秒
            }
        } catch (error) {
            console.error('轮询状态失败:', error);
            setTimeout(poll, 3000);
        }
    };
    
    poll();
}

function resetPipelineState() {
    state.isRunning = false;
    updateStatus('就绪', false);
    
    const startBtn = document.getElementById('startBtn');
    startBtn.disabled = false;
    startBtn.innerHTML = `
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polygon points="5 3 19 12 5 21 5 3"/>
        </svg>
        <span>启动流水线</span>
    `;
}

function cancelPipeline() {
    state.isRunning = false;
    updateStatus('已取消', false);
    addLog('用户取消了流水线', 'warning');
    resetPipelineState();
    
    fetch(`${API_BASE}/api/cancel`, { method: 'POST' })
        .catch(console.error);
}

// ============================================
// 文章管理
// ============================================

async function loadArticles() {
    const container = document.getElementById('articlesContainer');
    
    try {
        const response = await fetch(`${API_BASE}/api/articles`);
        const data = await response.json();
        
        state.articles = data.articles || [];
        renderArticles();
    } catch (error) {
        console.error('加载文章失败:', error);
        container.innerHTML = `<div class="empty-state"><p class="empty-desc">加载失败</p></div>`;
    }
}

function renderArticles() {
    const container = document.getElementById('articlesContainer');
    const countBadge = document.getElementById('articleCountBadge');
    
    countBadge.textContent = `${state.articles.length} 篇`;
    
    if (state.articles.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="empty-illustration">
                    <svg width="80" height="80" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1">
                        <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
                        <polyline points="14 2 14 8 20 8"/>
                        <line x1="12" y1="18" x2="12" y2="12"/>
                        <line x1="9" y1="15" x2="15" y2="15"/>
                    </svg>
                </div>
                <h3 class="empty-title">暂无文章</h3>
                <p class="empty-desc">选择RSS源并启动流水线来生成文章</p>
            </div>
        `;
        return;
    }
    
    container.innerHTML = state.articles.map(article => `
        <div class="article-card">
            <div class="article-header">
                <h3 class="article-title">${escapeHtml(article.title)}</h3>
                <span class="status-badge ${article.published ? 'success' : 'pending'}">
                    ${article.published ? '已发布' : '待发布'}
                </span>
            </div>
            <div class="article-meta">
                <div class="meta-item">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>
                        <line x1="16" y1="2" x2="16" y2="6"/>
                        <line x1="8" y1="2" x2="8" y2="6"/>
                        <line x1="3" y1="10" x2="21" y2="10"/>
                    </svg>
                    ${formatDate(article.date)}
                </div>
                <div class="meta-item">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
                        <polyline points="14 2 14 8 20 8"/>
                        <line x1="16" y1="13" x2="8" y2="13"/>
                        <line x1="16" y1="17" x2="8" y2="17"/>
                    </svg>
                    ${article.wordCount || 0} 字
                </div>
            </div>
            <div class="article-actions">
                <button class="btn btn-sm btn-ghost" onclick="previewArticle('${article.id}')">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                        <circle cx="12" cy="12" r="3"/>
                    </svg>
                    预览
                </button>
                <button class="btn btn-sm btn-primary" onclick="publishArticle('${article.id}')" ${article.published ? 'disabled' : ''}>
                    ${article.published ? '已发布' : '发布'}
                </button>
            </div>
        </div>
    `).join('');
}

function formatDate(dateStr) {
    const d = new Date(dateStr);
    return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
}

async function previewArticle(id) {
    const article = state.articles.find(a => a.id === id);
    if (!article) return;
    
    // 简单预览，可以扩展为模态框
    window.open(`${API_BASE}/api/articles/${id}`, '_blank');
}

async function publishArticle(id) {
    try {
        const response = await fetch(`${API_BASE}/api/articles/${id}/publish`, { method: 'POST' });
        const result = await response.json();
        
        if (result.status === 'success') {
            showToast('文章发布成功', 'success');
            loadArticles();
        } else {
            throw new Error(result.message);
        }
    } catch (error) {
        showToast(`发布失败: ${error.message}`, 'error');
    }
}

function showArticles() {
    // 滚动到文章区域
    document.querySelector('.articles-section').scrollIntoView({ behavior: 'smooth' });
}

// ============================================
// 工具函数
// ============================================

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 添加CSS动画类
const style = document.createElement('style');
style.textContent = `
    @keyframes spin {
        from { transform: rotate(0deg); }
        to { transform: rotate(360deg); }
    }
    .animate-spin {
        animation: spin 1s linear infinite;
    }
`;
document.head.appendChild(style);

// 初始化
document.addEventListener('DOMContentLoaded', () => {
    loadRssSources();
    loadArticles();
});
// 博客流水线前端脚本

// 状态管理
let config = null;
let currentArticle = null;

// 初始化
document.addEventListener('DOMContentLoaded', () => {
    initNavigation();
    initForms();
    loadConfig();
    loadStats();
    initDatePicker();
});

// 导航
function initNavigation() {
    document.querySelectorAll('.nav-item').forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const tab = item.dataset.tab;
            switchTab(tab);
        });
    });
}

function switchTab(tabName) {
    // 更新导航
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.toggle('active', item.dataset.tab === tabName);
    });
    
    // 更新内容
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.toggle('active', content.id === `tab-${tabName}`);
    });
    
    // 加载特定数据
    if (tabName === 'logs') loadLogs();
    if (tabName === 'rss') loadRssSources();
    if (tabName === 'content') loadArticles();
}

// API调用封装
async function api(endpoint, method = 'GET', data = null) {
    const options = {
        method,
        headers: {'Content-Type': 'application/json'}
    };
    if (data) options.body = JSON.stringify(data);
    
    const response = await fetch(`/api${endpoint}`, options);
    const result = await response.json();
    
    if (!response.ok) {
        throw new Error(result.error || '请求失败');
    }
    
    return result;
}

// 加载遮罩
function showLoading(text = '处理中...') {
    const overlay = document.getElementById('loading-overlay');
    document.getElementById('loading-text').textContent = text;
    overlay.style.display = 'flex';
}

function hideLoading() {
    document.getElementById('loading-overlay').style.display = 'none';
}

// 通知
function showToast(message, type = 'success') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <i class="ri-${type === 'success' ? 'check' : type === 'error' ? 'error-warning' : 'information'}-line"></i>
        <span>${message}</span>
    `;
    container.appendChild(toast);
    
    setTimeout(() => toast.remove(), 3000);
}

// 加载配置
async function loadConfig() {
    try {
        config = await api('/config');
        populateSettings(config);
    } catch (e) {
        console.error('加载配置失败:', e);
    }
}

// 填充设置
function populateSettings(config) {
    // AI设置
    const aiConfig = config.ai || {};
    document.getElementById('ai-provider').value = aiConfig.provider || 'openai';
    document.getElementById('ai-api-key').value = aiConfig.api_key || '';
    document.getElementById('ai-base-url').value = aiConfig.base_url || 'https://api.openai.com/v1';
    document.getElementById('ai-model').value = aiConfig.model || 'gpt-4o-mini';
    
    // 配图设置
    const imageConfig = config.image || {};
    document.getElementById('image-enabled').checked = imageConfig.enabled !== false;
    document.getElementById('image-provider').value = imageConfig.provider || 'dalle';
    document.getElementById('image-api-key').value = imageConfig.api_key || '';
    
    // 内容设置
    const contentConfig = config.content || {};
    document.getElementById('content-summary-length').value = contentConfig.summary_length || 200;
    document.getElementById('content-article-length').value = contentConfig.article_length || 1500;
    document.getElementById('content-language').value = contentConfig.language || 'zh-CN';
    document.getElementById('content-include-source').checked = contentConfig.include_source !== false;
    
    // 定时任务
    const schedulerConfig = config.scheduler || {};
    document.getElementById('scheduler-enabled').checked = schedulerConfig.enabled || false;
    document.getElementById('scheduler-interval').value = config.rss?.fetch_interval || 3600;
    document.getElementById('scheduler-timezone').value = schedulerConfig.timezone || 'Asia/Shanghai';
    
    // 发布设置
    const publishConfig = config.publish || {};
    
    const localConfig = publishConfig.local || {};
    document.getElementById('pub-local-enabled').checked = localConfig.enabled !== false;
    document.getElementById('pub-local-type').value = localConfig.type || 'hugo';
    document.getElementById('pub-local-dir').value = localConfig.content_dir || './output/posts';
    
    const githubConfig = publishConfig.github || {};
    document.getElementById('pub-github-enabled').checked = githubConfig.enabled || false;
    document.getElementById('pub-github-repo').value = githubConfig.repo || '';
    document.getElementById('pub-github-branch').value = githubConfig.branch || 'main';
    document.getElementById('pub-github-token').value = githubConfig.token || '';
    
    const wpConfig = publishConfig.wordpress || {};
    document.getElementById('pub-wordpress-enabled').checked = wpConfig.enabled || false;
    document.getElementById('pub-wordpress-url').value = wpConfig.url || '';
    document.getElementById('pub-wordpress-username').value = wpConfig.username || '';
    document.getElementById('pub-wordpress-password').value = wpConfig.password || '';
    
    const webhookConfig = publishConfig.webhook || {};
    document.getElementById('pub-webhook-enabled').checked = webhookConfig.enabled || false;
    document.getElementById('pub-webhook-url').value = webhookConfig.url || '';
    document.getElementById('pub-webhook-headers').value = JSON.stringify(webhookConfig.headers || {});
}

// 加载统计
async function loadStats() {
    try {
        const status = await api('/status');
        document.getElementById('stat-rss-sources').textContent = status.rss_sources || 0;
        document.getElementById('stat-targets').textContent = status.publish_targets || 0;
        
        if (status.scheduler_running) {
            document.getElementById('scheduler-status').innerHTML = `
                <span class="dot active"></span>
                <span>定时任务: 运行中</span>
            `;
        }
    } catch (e) {
        console.error('加载状态失败:', e);
    }
    
    // 加载文章统计
    try {
        const posts = await api('/posts');
        document.getElementById('stat-articles').textContent = posts.posts?.length || 0;
        document.getElementById('stat-published').textContent = posts.posts?.length || 0;
    } catch (e) {
        console.error('加载文章失败:', e);
    }
}

// 表单初始化
function initForms() {
    // 添加RSS源
    document.getElementById('form-add-rss').addEventListener('submit', async (e) => {
        e.preventDefault();
        const name = document.getElementById('rss-name').value;
        const url = document.getElementById('rss-url').value;
        
        if (!name || !url) {
            showToast('请填写完整信息', 'error');
            return;
        }
        
        try {
            showLoading('添加RSS源...');
            if (!config.rss) config.rss = {sources: []};
            config.rss.sources.push({name, url, enabled: true});
            await api('/config', 'POST', config);
            showToast('RSS源已添加');
            loadRssSources();
            document.getElementById('form-add-rss').reset();
        } catch (e) {
            showToast(e.message, 'error');
        } finally {
            hideLoading();
        }
    });
    
    // 生成文章
    document.getElementById('form-generate').addEventListener('submit', async (e) => {
        e.preventDefault();
        const title = document.getElementById('gen-title').value;
        const content = document.getElementById('gen-content').value;
        const sourceUrl = document.getElementById('gen-source').value;
        
        if (!title) {
            showToast('请填写标题', 'error');
            return;
        }
        
        try {
            showLoading('生成文章中...');
            const result = await api('/content/generate', 'POST', {
                title, content, source_url: sourceUrl
            });
            
            currentArticle = result.article;
            showArticleResult(result.article);
            showToast('文章已生成');
        } catch (e) {
            showToast(e.message, 'error');
        } finally {
            hideLoading();
        }
    });
    
    // 保存设置
    document.getElementById('btn-save-settings').addEventListener('click', saveAllSettings);
    document.getElementById('btn-save-publish').addEventListener('click', savePublishSettings);
    
    // 发布结果
    document.getElementById('btn-publish-result').addEventListener('click', publishCurrentArticle);
    document.getElementById('btn-copy-result').addEventListener('click', copyArticleContent);
    
    // 快速操作
    document.getElementById('btn-run-pipeline').addEventListener('click', runPipeline);
    document.getElementById('btn-fetch-rss').addEventListener('click', fetchRss);
    document.getElementById('btn-start-scheduler').addEventListener('click', toggleScheduler);
    document.getElementById('btn-preview-rss').addEventListener('click', previewRss);
    document.getElementById('btn-refresh-logs').addEventListener('click', loadLogs);
    
    // 加载RSS源列表
    loadRssSources();
    
    // 加载文章列表
    loadArticles();
}

// 保存设置
async function saveAllSettings() {
    try {
        showLoading('保存设置...');
        
        config = config || {};
        
        // AI设置
        config.ai = {
            provider: document.getElementById('ai-provider').value,
            api_key: document.getElementById('ai-api-key').value,
            base_url: document.getElementById('ai-base-url').value,
            model: document.getElementById('ai-model').value
        };
        
        // 配图设置
        config.image = {
            enabled: document.getElementById('image-enabled').checked,
            provider: document.getElementById('image-provider').value,
            api_key: document.getElementById('image-api-key').value
        };
        
        // 内容设置
        config.content = {
            summary_length: parseInt(document.getElementById('content-summary-length').value),
            article_length: parseInt(document.getElementById('content-article-length').value),
            language: document.getElementById('content-language').value,
            include_source: document.getElementById('content-include-source').checked
        };
        
        // 定时任务
        config.scheduler = {
            enabled: document.getElementById('scheduler-enabled').checked,
            timezone: document.getElementById('scheduler-timezone').value
        };
        
        config.rss = config.rss || {};
        config.rss.fetch_interval = parseInt(document.getElementById('scheduler-interval').value);
        
        await api('/config', 'POST', config);
        showToast('设置已保存');
    } catch (e) {
        showToast(e.message, 'error');
    } finally {
        hideLoading();
    }
}

// 保存发布设置
async function savePublishSettings() {
    try {
        showLoading('保存发布设置...');
        
        config = config || {};
        config.publish = {
            local: {
                enabled: document.getElementById('pub-local-enabled').checked,
                type: document.getElementById('pub-local-type').value,
                content_dir: document.getElementById('pub-local-dir').value
            },
            github: {
                enabled: document.getElementById('pub-github-enabled').checked,
                repo: document.getElementById('pub-github-repo').value,
                branch: document.getElementById('pub-github-branch').value,
                token: document.getElementById('pub-github-token').value
            },
            wordpress: {
                enabled: document.getElementById('pub-wordpress-enabled').checked,
                url: document.getElementById('pub-wordpress-url').value,
                username: document.getElementById('pub-wordpress-username').value,
                password: document.getElementById('pub-wordpress-password').value
            },
            webhook: {
                enabled: document.getElementById('pub-webhook-enabled').checked,
                url: document.getElementById('pub-webhook-url').value,
                headers: JSON.parse(document.getElementById('pub-webhook-headers').value || '{}')
            }
        };
        
        await api('/config', 'POST', config);
        showToast('发布设置已保存');
        loadStats();
    } catch (e) {
        showToast(e.message, 'error');
    } finally {
        hideLoading();
    }
}

// 加载RSS源
function loadRssSources() {
    if (!config?.rss?.sources) {
        document.getElementById('rss-list').innerHTML = '<p class="placeholder">暂无RSS源</p>';
        return;
    }
    
    const sources = config.rss.sources;
    if (sources.length === 0) {
        document.getElementById('rss-list').innerHTML = '<p class="placeholder">暂无RSS源</p>';
        return;
    }
    
    const html = sources.map((source, index) => `
        <div class="list-item">
            <div class="list-item-info">
                <div class="list-item-title">${source.name}</div>
                <div class="list-item-meta">${source.url}</div>
            </div>
            <div class="list-item-actions">
                <button onclick="toggleRssSource(${index})" title="${source.enabled ? '禁用' : '启用'}">
                    <i class="ri-${source.enabled ? 'toggle-fill' : 'toggle-line'}"></i>
                </button>
                <button onclick="removeRssSource(${index})" title="删除">
                    <i class="ri-delete-bin-line"></i>
                </button>
            </div>
        </div>
    `).join('');
    
    document.getElementById('rss-list').innerHTML = html;
}

// 切换RSS源状态
async function toggleRssSource(index) {
    config.rss.sources[index].enabled = !config.rss.sources[index].enabled;
    await api('/config', 'POST', config);
    loadRssSources();
}

// 删除RSS源
async function removeRssSource(index) {
    if (!confirm('确定要删除此RSS源吗？')) return;
    
    config.rss.sources.splice(index, 1);
    await api('/config', 'POST', config);
    loadRssSources();
    loadStats();
    showToast('RSS源已删除');
}

// 预览RSS
async function previewRss() {
    try {
        showLoading('抓取RSS内容...');
        const result = await api('/rss/fetch', 'POST');
        
        if (result.items.length === 0) {
            document.getElementById('rss-preview').innerHTML = '<p class="placeholder">未获取到内容</p>';
            return;
        }
        
        const html = result.items.slice(0, 10).map(item => `
            <div class="list-item">
                <div class="list-item-info">
                    <div class="list-item-title">${item.title}</div>
                    <div class="list-item-meta">${item.source_name} · ${new Date(item.published).toLocaleDateString()}</div>
                </div>
                <button class="btn btn-sm btn-secondary" onclick="useRssItem('${item.title.replace(/'/g, "\\'")}', '${item.link}')">
                    使用
                </button>
            </div>
        `).join('');
        
        document.getElementById('rss-preview').innerHTML = html;
        showToast(`获取到 ${result.count} 条内容`);
    } catch (e) {
        showToast(e.message, 'error');
    } finally {
        hideLoading();
    }
}

// 使用RSS条目
function useRssItem(title, url) {
    switchTab('content');
    document.getElementById('gen-title').value = title;
    document.getElementById('gen-source').value = url;
}

// 显示文章结果
function showArticleResult(article) {
    document.getElementById('result-panel').style.display = 'block';
    document.getElementById('result-title').textContent = article.title;
    
    const tagsHtml = article.tags?.map(t => `<span>${t}</span>`).join('') || '';
    document.getElementById('result-tags').innerHTML = tagsHtml;
    
    if (article.image_url) {
        document.getElementById('result-image').innerHTML = `<img src="${article.image_url}" style="max-width:100%;border-radius:8px;">`;
    } else {
        document.getElementById('result-image').innerHTML = '';
    }
    
    document.getElementById('result-content').textContent = article.content;
    
    // 滚动到结果
    document.getElementById('result-panel').scrollIntoView({behavior: 'smooth'});
}

// 发布当前文章
async function publishCurrentArticle() {
    if (!currentArticle) {
        showToast('没有可发布的文章', 'error');
        return;
    }
    
    try {
        showLoading('发布中...');
        const result = await api('/publish', 'POST', currentArticle);
        showToast('发布成功');
        loadStats();
        loadArticles();
    } catch (e) {
        showToast(e.message, 'error');
    } finally {
        hideLoading();
    }
}

// 复制文章内容
function copyArticleContent() {
    if (!currentArticle) return;
    
    const text = `# ${currentArticle.title}\n\n${currentArticle.content}`;
    navigator.clipboard.writeText(text).then(() => {
        showToast('已复制到剪贴板');
    });
}

// 加载文章列表
async function loadArticles() {
    try {
        const result = await api('/posts');
        const posts = result.posts || [];
        
        if (posts.length === 0) {
            document.getElementById('articles-list').innerHTML = '<p class="placeholder">暂无文章</p>';
            return;
        }
        
        const html = posts.map(post => `
            <div class="list-item">
                <div class="list-item-info">
                    <div class="list-item-title">${post.title}</div>
                    <div class="list-item-meta">${post.date || '未知日期'} · ${post.tags?.join(', ') || ''}</div>
                </div>
                <div class="list-item-actions">
                    <button onclick="viewArticle('${post.filename}')" title="查看">
                        <i class="ri-eye-line"></i>
                    </button>
                </div>
            </div>
        `).join('');
        
        document.getElementById('articles-list').innerHTML = html;
    } catch (e) {
        document.getElementById('articles-list').innerHTML = '<p class="placeholder">加载失败</p>';
    }
}

// 运行完整流水线
async function runPipeline() {
    if (!confirm('确定要运行完整流水线吗？这将自动抓取RSS、生成文章并发布。')) return;
    
    try {
        showLoading('运行流水线中...');
        const result = await api('/pipeline', 'POST');
        showToast(`处理完成: ${result.processed} 篇文章`);
        loadStats();
        loadArticles();
    } catch (e) {
        showToast(e.message, 'error');
    } finally {
        hideLoading();
    }
}

// 抓取RSS
async function fetchRss() {
    try {
        showLoading('抓取RSS...');
        const result = await api('/rss/fetch', 'POST');
        showToast(`获取到 ${result.count} 条内容`);
        
        // 跳转到RSS页面查看
        switchTab('rss');
        previewRss();
    } catch (e) {
        showToast(e.message, 'error');
    } finally {
        hideLoading();
    }
}

// 切换定时任务
let schedulerRunning = false;

async function toggleScheduler() {
    try {
        if (schedulerRunning) {
            await api('/scheduler/stop', 'POST');
            schedulerRunning = false;
            showToast('定时任务已停止');
            document.getElementById('scheduler-status').innerHTML = `
                <span class="dot"></span>
                <span>定时任务: 已停止</span>
            `;
        } else {
            await api('/scheduler/start', 'POST');
            schedulerRunning = true;
            showToast('定时任务已启动');
            document.getElementById('scheduler-status').innerHTML = `
                <span class="dot active"></span>
                <span>定时任务: 运行中</span>
            `;
        }
    } catch (e) {
        showToast(e.message, 'error');
    }
}

// 日期选择器
function initDatePicker() {
    const today = new Date().toISOString().split('T')[0];
    document.getElementById('log-date').value = today;
}

// 加载日志
async function loadLogs() {
    const date = document.getElementById('log-date').value;
    
    try {
        const result = await api(`/logs?date=${date}`);
        const logs = result.logs || [];
        
        if (logs.length === 0) {
            document.getElementById('log-container').innerHTML = '<p class="placeholder">暂无日志</p>';
            return;
        }
        
        const html = logs.map(log => {
            const cls = log.includes('[ERROR]') ? 'ERROR' : log.includes('[WARNING]') ? 'WARNING' : 'INFO';
            return `<div class="log-line ${cls}">${escapeHtml(log)}</div>`;
        }).join('');
        
        document.getElementById('log-container').innerHTML = html;
        document.getElementById('log-container').scrollTop = document.getElementById('log-container').scrollHeight;
    } catch (e) {
        document.getElementById('log-container').innerHTML = '<p class="placeholder">加载失败</p>';
    }
}

// HTML转义
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 查看文章
async function viewArticle(filename) {
    try {
        // 这里可以打开一个模态框或跳转到编辑页面
        showToast('查看文章: ' + filename);
    } catch (e) {
        showToast(e.message, 'error');
    }
}
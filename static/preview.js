// 预览页面脚本

const API_BASE = window.location.origin;
let currentFile = null;
let selectedText = '';
let selectedStart = 0;
let selectedEnd = 0;

// 初始化
function initPreview() {
    // 从 URL 获取文件名
    const params = new URLSearchParams(window.location.search);
    currentFile = params.get('file');
    
    if (!currentFile) {
        showToast('未指定文章', 'error');
        return;
    }
    
    // 加载文章内容
    loadArticle();
    
    // 监听编辑器事件
    setupEditorEvents();
    
    // 监听 AI 输入事件
    setupAIInputEvents();
}

// 加载文章
function loadArticle() {
    fetch(`${API_BASE}/api/articles/${encodeURIComponent(currentFile)}`)
        .then(r => r.json())
        .then(data => {
            if (data.error) {
                showToast(data.error, 'error');
                return;
            }
            document.getElementById('articleTitle').value = data.title || '';
            document.getElementById('editor').value = data.content || '';
            updateWordCount();
        })
        .catch(err => showToast('加载失败: ' + err.message, 'error'));
}

// 设置编辑器事件
function setupEditorEvents() {
    const editor = document.getElementById('editor');
    
    // 选中文字事件
    editor.addEventListener('select', () => {
        const start = editor.selectionStart;
        const end = editor.selectionEnd;
        const text = editor.value.substring(start, end);
        
        if (text.length > 0) {
            selectedText = text;
            selectedStart = start;
            selectedEnd = end;
            showSelectedPreview(text);
            document.getElementById('selectionInfo').textContent = `已选 ${text.length} 字`;
        } else {
            clearSelection();
        }
    });
    
    // 输入事件更新字数
    editor.addEventListener('input', updateWordCount);
    
    // 键盘快捷键
    editor.addEventListener('keydown', (e) => {
        if (e.ctrlKey || e.metaKey) {
            if (e.key === 's') {
                e.preventDefault();
                saveArticle();
            }
        }
    });
}

// 设置 AI 输入事件
function setupAIInputEvents() {
    const aiInput = document.getElementById('aiInput');
    
    aiInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendAIRequest();
        }
    });
}

// 显示选中预览
function showSelectedPreview(text) {
    const preview = document.getElementById('selectedPreview');
    const previewText = document.getElementById('selectedTextPreview');
    preview.style.display = 'block';
    previewText.textContent = text.length > 100 ? text.substring(0, 100) + '...' : text;
}

// 清除选中
function clearSelection() {
    selectedText = '';
    selectedStart = 0;
    selectedEnd = 0;
    document.getElementById('selectedPreview').style.display = 'none';
    document.getElementById('selectionInfo').textContent = '未选中';
}

// 更新字数
function updateWordCount() {
    const text = document.getElementById('editor').value;
    // 统计中文字符和英文单词
    const chineseChars = (text.match(/[\u4e00-\u9fa5]/g) || []).length;
    const englishWords = (text.match(/[a-zA-Z]+/g) || []).length;
    const total = chineseChars + englishWords;
    document.getElementById('wordCount').textContent = `${total} 字`;
}

// 插入格式
function insertFormat(before, after) {
    const editor = document.getElementById('editor');
    const start = editor.selectionStart;
    const end = editor.selectionEnd;
    const text = editor.value;
    
    if (start === end) {
        // 无选中，直接插入
        editor.value = text.substring(0, start) + before + after + text.substring(end);
        editor.selectionStart = start + before.length;
        editor.selectionEnd = start + before.length;
    } else {
        // 有选中，包裹
        const selected = text.substring(start, end);
        editor.value = text.substring(0, start) + before + selected + after + text.substring(end);
        editor.selectionStart = start;
        editor.selectionEnd = end + before.length + after.length;
    }
    
    editor.focus();
    updateWordCount();
}

// 使用示例
function useExample(text) {
    document.getElementById('aiInput').value = text;
}

// 发送 AI 请求
async function sendAIRequest() {
    const input = document.getElementById('aiInput');
    const request = input.value.trim();
    
    if (!request) {
        showToast('请输入修改需求', 'error');
        return;
    }
    
    // 获取选中文字（如果没有预存的选中，尝试获取当前选中）
    const editor = document.getElementById('editor');
    if (!selectedText) {
        const start = editor.selectionStart;
        const end = editor.selectionEnd;
        selectedText = editor.value.substring(start, end);
        selectedStart = start;
        selectedEnd = end;
    }
    
    if (!selectedText) {
        showToast('请先选中要修改的文字', 'error');
        return;
    }
    
    // 显示用户消息
    addChatMessage('user', request, selectedText);
    
    // 清空输入
    input.value = '';
    
    // 显示加载
    showLoading();
    
    try {
        const response = await fetch(`${API_BASE}/api/articles/${encodeURIComponent(currentFile)}/ai-modify`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                selected_text: selectedText,
                request: request,
                full_content: editor.value
            })
        });
        
        const result = await response.json();
        
        hideLoading();
        
        if (result.error) {
            addChatMessage('ai', `❌ ${result.error}`);
        } else {
            addChatMessage('ai', result.suggestion, null, result.new_text);
        }
        
    } catch (err) {
        hideLoading();
        addChatMessage('ai', `❌ 请求失败: ${err.message}`);
    }
}

// 添加聊天消息
function addChatMessage(type, content, selectedText, newText) {
    const container = document.getElementById('chatContainer');
    
    // 移除欢迎消息
    const welcome = container.querySelector('.chat-welcome');
    if (welcome) welcome.remove();
    
    const msgDiv = document.createElement('div');
    msgDiv.className = `chat-message message-${type}`;
    
    if (type === 'user') {
        msgDiv.innerHTML = `
            <div class="message-header">
                <span>你</span>
            </div>
            ${selectedText ? `<div class="message-selected">"${selectedText.length > 50 ? selectedText.substring(0, 50) + '...' : selectedText}"</div>` : ''}
            <div class="message-content">${content}</div>
        `;
    } else {
        msgDiv.innerHTML = `
            <div class="message-header">
                <span>AI 助手</span>
            </div>
            <div class="message-content">${content}</div>
            ${newText ? `
                <div class="message-actions">
                    <button class="action-btn action-btn-apply" onclick="applySuggestion('${escapeHtml(newText)}')">应用修改</button>
                    <button class="action-btn" onclick="copyText('${escapeHtml(newText)}')">复制</button>
                </div>
            ` : ''}
        `;
    }
    
    container.appendChild(msgDiv);
    container.scrollTop = container.scrollHeight;
}

// 显示加载
function showLoading() {
    const container = document.getElementById('chatContainer');
    const loadingDiv = document.createElement('div');
    loadingDiv.className = 'chat-message message-ai message-loading';
    loadingDiv.id = 'loadingMessage';
    loadingDiv.innerHTML = `
        <div class="loading-spinner"></div>
        <span>AI 正在思考...</span>
    `;
    container.appendChild(loadingDiv);
    container.scrollTop = container.scrollHeight;
}

// 隐藏加载
function hideLoading() {
    const loading = document.getElementById('loadingMessage');
    if (loading) loading.remove();
}

// 应用建议
function applySuggestion(newText) {
    const editor = document.getElementById('editor');
    
    // 替换选中文字
    const before = editor.value.substring(0, selectedStart);
    const after = editor.value.substring(selectedEnd);
    editor.value = before + newText + after;
    
    // 更新选中位置
    const newEnd = selectedStart + newText.length;
    editor.selectionStart = selectedStart;
    editor.selectionEnd = newEnd;
    
    // 更新预存的选中
    selectedText = newText;
    selectedEnd = newEnd;
    showSelectedPreview(newText);
    
    editor.focus();
    updateWordCount();
    
    showToast('已应用修改', 'success');
}

// 复制文本
function copyText(text) {
    navigator.clipboard.writeText(text)
        .then(() => showToast('已复制', 'success'))
        .catch(() => showToast('复制失败', 'error'));
}

// 保存文章
async function saveArticle() {
    const title = document.getElementById('articleTitle').value;
    const content = document.getElementById('editor').value;
    
    try {
        const response = await fetch(`${API_BASE}/api/articles/${encodeURIComponent(currentFile)}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title, content })
        });
        
        const result = await response.json();
        
        if (result.status === 'success') {
            showToast('保存成功', 'success');
        } else {
            showToast(result.message || '保存失败', 'error');
        }
    } catch (err) {
        showToast('保存失败: ' + err.message, 'error');
    }
}

// 发布并返回
async function publishAndReturn() {
    // 先保存
    await saveArticle();
    
    // 发布
    try {
        const response = await fetch(`${API_BASE}/api/articles/${encodeURIComponent(currentFile)}/publish`, {
            method: 'POST'
        });
        
        const result = await response.json();
        
        if (result.status === 'success') {
            showToast('发布成功', 'success');
            // 返回工作台
            setTimeout(() => window.location.href = '/', 1000);
        } else {
            showToast(result.message || '发布失败', 'error');
        }
    } catch (err) {
        showToast('发布失败: ' + err.message, 'error');
    }
}

// Toast 通知
function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
        <span class="toast-icon">${type === 'success' ? '✓' : type === 'error' ? '✗' : 'ℹ'}</span>
        <span class="toast-message">${message}</span>
    `;
    container.appendChild(toast);
    
    setTimeout(() => {
        toast.classList.add('fade-out');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// HTML 转义
function escapeHtml(text) {
    return text.replace(/&/g, '&amp;')
               .replace(/'/g, '&#39;')
               .replace(/"/g, '&quot;');
}
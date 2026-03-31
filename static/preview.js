// 预览页面脚本

const API_BASE = window.location.origin;
let currentFile = null;
let selectedText = '';
let selectedStart = 0;
let selectedEnd = 0;

// 初始化
function initPreview() {
    // 从 URL 路径获取 article_id (格式: /preview/article_id)
    const pathParts = window.location.pathname.split('/');
    const articleId = pathParts[pathParts.length - 1];
    
    if (!articleId) {
        showToast('未指定文章', 'error');
        return;
    }
    
    // 加载文章内容
    loadArticle(articleId);
    
    // 监听编辑器事件
    setupEditorEvents();
    
    // 监听 AI 输入事件
    setupAIInputEvents();
}

// 加载文章
function loadArticle(articleId) {
    fetch(API_BASE + '/api/article/' + articleId)
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (data.error) {
                showToast(data.error, 'error');
                return;
            }
            currentFile = data.file;
            document.getElementById('articleTitle').value = data.title || '';
            document.getElementById('editor').value = data.content || '';
            updateWordCount();
        })
        .catch(function(err) { showToast('加载失败: ' + err.message, 'error'); });
}

// 设置编辑器事件
function setupEditorEvents() {
    var editor = document.getElementById('editor');
    
    // 选中文字事件
    editor.addEventListener('select', function() {
        var start = editor.selectionStart;
        var end = editor.selectionEnd;
        var text = editor.value.substring(start, end);
        
        if (text.length > 0) {
            selectedText = text;
            selectedStart = start;
            selectedEnd = end;
            showSelectedPreview(text);
            document.getElementById('selectionInfo').textContent = '已选 ' + text.length + ' 字';
        } else {
            clearSelection();
        }
    });
    
    // 输入事件更新字数
    editor.addEventListener('input', updateWordCount);
    
    // 键盘快捷键
    editor.addEventListener('keydown', function(e) {
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
    var aiInput = document.getElementById('aiInput');
    aiInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendAIRequest();
        }
    });
}

// 显示选中预览
function showSelectedPreview(text) {
    var preview = document.getElementById('selectedPreview');
    var previewText = document.getElementById('selectedTextPreview');
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
    var text = document.getElementById('editor').value;
    var chineseChars = (text.match(/[\u4e00-\u9fa5]/g) || []).length;
    var englishWords = (text.match(/[a-zA-Z]+/g) || []).length;
    var total = chineseChars + englishWords;
    document.getElementById('wordCount').textContent = total + ' 字';
}

// 插入格式
function insertFormat(before, after) {
    var editor = document.getElementById('editor');
    var start = editor.selectionStart;
    var end = editor.selectionEnd;
    var text = editor.value;
    
    if (start === end) {
        editor.value = text.substring(0, start) + before + after + text.substring(end);
        editor.selectionStart = start + before.length;
        editor.selectionEnd = start + before.length;
    } else {
        var selected = text.substring(start, end);
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
function sendAIRequest() {
    var input = document.getElementById('aiInput');
    var request = input.value.trim();
    
    if (!request) {
        showToast('请输入修改需求', 'error');
        return;
    }
    
    var editor = document.getElementById('editor');
    if (!selectedText) {
        var start = editor.selectionStart;
        var end = editor.selectionEnd;
        selectedText = editor.value.substring(start, end);
        selectedStart = start;
        selectedEnd = end;
    }
    
    if (!selectedText) {
        showToast('请先选中要修改的文字', 'error');
        return;
    }
    
    addChatMessage('user', request, selectedText);
    input.value = '';
    showLoading();
    
    fetch(API_BASE + '/api/articles/' + encodeURIComponent(currentFile) + '/ai-modify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            selected_text: selectedText,
            request: request,
            full_content: editor.value
        })
    })
    .then(function(r) { return r.json(); })
    .then(function(result) {
        hideLoading();
        if (result.error) {
            addChatMessage('ai', '❌ ' + result.error);
        } else {
            addChatMessage('ai', result.suggestion, null, result.new_text);
        }
    })
    .catch(function(err) {
        hideLoading();
        addChatMessage('ai', '❌ 请求失败: ' + err.message);
    });
}

// 添加聊天消息
function addChatMessage(type, content, selText, newText) {
    var container = document.getElementById('chatContainer');
    
    var welcome = container.querySelector('.chat-welcome');
    if (welcome) welcome.remove();
    
    var msgDiv = document.createElement('div');
    msgDiv.className = 'chat-message message-' + type;
    
    if (type === 'user') {
        msgDiv.innerHTML = '<div class="message-header"><span>你</span></div>' +
            (selText ? '<div class="message-selected">"' + (selText.length > 50 ? selText.substring(0, 50) + '...' : selText) + '"</div>' : '') +
            '<div class="message-content">' + content + '</div>';
    } else {
        msgDiv.innerHTML = '<div class="message-header"><span>AI 助手</span></div>' +
            '<div class="message-content">' + content + '</div>' +
            (newText ? '<div class="message-actions"><button class="action-btn action-btn-apply" onclick="applySuggestion(\'' + escapeHtml(newText) + '\')">应用修改</button><button class="action-btn" onclick="copyText(\'' + escapeHtml(newText) + '\')">复制</button></div>' : '');
    }
    
    container.appendChild(msgDiv);
    container.scrollTop = container.scrollHeight;
}

// 显示加载
function showLoading() {
    var container = document.getElementById('chatContainer');
    var loadingDiv = document.createElement('div');
    loadingDiv.className = 'chat-message message-ai message-loading';
    loadingDiv.id = 'loadingMessage';
    loadingDiv.innerHTML = '<div class="loading-spinner"></div><span>AI 正在思考...</span>';
    container.appendChild(loadingDiv);
    container.scrollTop = container.scrollHeight;
}

// 隐藏加载
function hideLoading() {
    var loading = document.getElementById('loadingMessage');
    if (loading) loading.remove();
}

// 应用建议
function applySuggestion(newText) {
    var editor = document.getElementById('editor');
    var before = editor.value.substring(0, selectedStart);
    var after = editor.value.substring(selectedEnd);
    editor.value = before + newText + after;
    
    var newEnd = selectedStart + newText.length;
    editor.selectionStart = selectedStart;
    editor.selectionEnd = newEnd;
    
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
        .then(function() { showToast('已复制', 'success'); })
        .catch(function() { showToast('复制失败', 'error'); });
}

// 保存文章
function saveArticle() {
    var title = document.getElementById('articleTitle').value;
    var content = document.getElementById('editor').value;
    
    fetch(API_BASE + '/api/articles/' + encodeURIComponent(currentFile), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: title, content: content })
    })
    .then(function(r) { return r.json(); })
    .then(function(result) {
        if (result.status === 'success') {
            showToast('保存成功', 'success');
        } else {
            showToast(result.message || '保存失败', 'error');
        }
    })
    .catch(function(err) { showToast('保存失败: ' + err.message, 'error'); });
}

// 发布并返回
function publishAndReturn() {
    var title = document.getElementById('articleTitle').value;
    var content = document.getElementById('editor').value;
    
    // currentFile 是完整文件名（如 xxx.md），需要去掉 .md 后缀作为 article_id
    var articleId = currentFile ? currentFile.replace(/\.md$/, '') : '';
    if (!articleId) {
        showToast('文章ID无效', 'error');
        return;
    }
    
    // 先保存，再发布
    fetch(API_BASE + '/api/articles/' + encodeURIComponent(currentFile), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: title, content: content })
    })
    .then(function(r) { return r.json(); })
    .then(function(saveResult) {
        if (saveResult.status !== 'success') {
            showToast('保存失败: ' + (saveResult.message || '未知错误'), 'error');
            return;
        }
        
        // 保存成功后发布
        return fetch(API_BASE + '/api/articles/' + encodeURIComponent(articleId) + '/publish', {
            method: 'POST'
        });
    })
    .then(function(r) { return r ? r.json() : null; })
    .then(function(result) {
        if (!result) return; // 保存失败时提前返回
        if (result.success) {
            showToast('发布成功', 'success');
            setTimeout(function() { window.location.href = '/'; }, 1000);
        } else {
            showToast(result.error || result.message || '发布失败', 'error');
        }
    })
    .catch(function(err) { showToast('操作失败: ' + err.message, 'error'); });
}

// Toast 通知
function showToast(message, type) {
    type = type || 'info';
    var container = document.getElementById('toastContainer');
    var toast = document.createElement('div');
    toast.className = 'toast toast-' + type;
    toast.innerHTML = '<span class="toast-icon">' + (type === 'success' ? '✓' : type === 'error' ? '✗' : 'ℹ') + '</span><span class="toast-message">' + message + '</span>';
    container.appendChild(toast);
    
    setTimeout(function() {
        toast.classList.add('fade-out');
        setTimeout(function() { toast.remove(); }, 300);
    }, 3000);
}

// HTML 转义
function escapeHtml(text) {
    return text.replace(/&/g, '\x26amp;')
               .replace(/</g, '\x26lt;')
               .replace(/>/g, '\x26gt;')
               .replace(/'/g, '\x26#39;')
               .replace(/"/g, '\x26quot;');
}

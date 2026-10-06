/**
 * CareerPearls - AI Resume Analyzer Chatbot Controller
 * Provides full chat persistence across page refreshes and hard reloads.
 */

let currentResumeText = "";
let currentJobId = null;
let chatHistory = [];
let currentAnalysisData = null;

function getResumeStorageKey(jobId) {
    const drawer = document.getElementById('cpRaDrawer');
    const userId = drawer ? (drawer.getAttribute('data-user-id') || 'guest') : 'guest';
    const jId = jobId || (drawer ? drawer.getAttribute('data-job-id') : '0');
    return `cp_ra_chat_u${userId}_job${jId}`;
}

function saveStateToLocal(jobId, analysisData, resumeText, messages) {
    try {
        const key = getResumeStorageKey(jobId);
        const payload = {
            jobId: jobId,
            analysisData: analysisData,
            resumeText: resumeText || "",
            messages: messages || [],
            savedAt: Date.now()
        };
        localStorage.setItem(key, JSON.stringify(payload));
    } catch (e) {
        console.warn('LocalStorage save error:', e);
    }
}

function loadStateFromLocal(jobId) {
    try {
        const key = getResumeStorageKey(jobId);
        const raw = localStorage.getItem(key);
        if (!raw) return null;
        return JSON.parse(raw);
    } catch (e) {
        return null;
    }
}

function clearStateFromLocal(jobId) {
    try {
        const key = getResumeStorageKey(jobId);
        localStorage.removeItem(key);
    } catch (e) {}
}

function openAiResumeAnalyzer() {
    const backdrop = document.getElementById('cpRaModalBackdrop');
    const drawer = document.getElementById('cpRaDrawer');
    if (!backdrop || !drawer) return;

    currentJobId = drawer.getAttribute('data-job-id');

    backdrop.classList.add('show');
    drawer.classList.add('show');
    document.body.style.overflow = 'hidden';

    setupDropzoneListeners();

    // 1. Instantly restore from LocalStorage if available (0ms render on reload)
    const localState = loadStateFromLocal(currentJobId);
    if (localState && localState.analysisData) {
        restoreAnalysisView(localState.analysisData, localState.resumeText, localState.messages);
    }

    // 2. Fetch latest synced history from server
    syncResumeChatHistory(currentJobId);
}

function closeAiResumeAnalyzer() {
    const backdrop = document.getElementById('cpRaModalBackdrop');
    const drawer = document.getElementById('cpRaDrawer');
    if (backdrop) backdrop.classList.remove('show');
    if (drawer) drawer.classList.remove('show');
    document.body.style.overflow = '';
}

function setupDropzoneListeners() {
    const dropzone = document.getElementById('cpRaDropzone');
    if (!dropzone || dropzone.dataset.initialized) return;

    dropzone.dataset.initialized = 'true';

    dropzone.addEventListener('click', () => {
        document.getElementById('cpRaFileInput').click();
    });

    dropzone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropzone.classList.add('dragover');
    });

    dropzone.addEventListener('dragleave', () => {
        dropzone.classList.remove('dragover');
    });

    dropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropzone.classList.remove('dragover');
        if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
            processResumeFileUpload(e.dataTransfer.files[0]);
        }
    });
}

function handleResumeFileSelect(event) {
    if (event.target.files && event.target.files.length > 0) {
        processResumeFileUpload(event.target.files[0]);
    }
}

function restoreAnalysisView(analysisData, resumeText, messages) {
    if (!analysisData) return;

    currentAnalysisData = analysisData;
    if (resumeText) currentResumeText = resumeText;

    const dropzone = document.getElementById('cpRaDropzone');
    const resultCard = document.getElementById('cpRaResultCard');
    const quickPrompts = document.getElementById('cpRaQuickPrompts');
    const messagesWin = document.getElementById('cpRaMessages');
    const input = document.getElementById('cpRaInput');
    const sendBtn = document.getElementById('cpRaSendBtn');
    const errorAlert = document.getElementById('cpRaErrorAlert');

    if (errorAlert) errorAlert.classList.add('d-none');
    if (dropzone) dropzone.classList.add('d-none');

    // Render Result Card
    renderAnalysisResultCard(analysisData);
    if (resultCard) resultCard.classList.remove('d-none');
    if (quickPrompts) quickPrompts.classList.remove('d-none');

    // Render Chat Messages
    if (messagesWin) {
        messagesWin.innerHTML = '';
        if (Array.isArray(messages)) {
            chatHistory = [{
                role: "assistant",
                content: analysisData.analysis_markdown || ""
            }];

            messages.forEach(msg => {
                if (msg.role === 'user' || msg.role === 'assistant') {
                    appendChatMessage(msg.role, msg.content || msg.text || '');
                    chatHistory.push({
                        role: msg.role,
                        content: msg.content || msg.text || ''
                    });
                }
            });
        }
    }

    if (input) {
        input.removeAttribute('disabled');
        input.focus();
    }
    if (sendBtn) sendBtn.removeAttribute('disabled');
}

async function syncResumeChatHistory(jobId) {
    if (!jobId) return;

    try {
        const response = await fetch(`/api/v1/resume-chat-history?job_id=${encodeURIComponent(jobId)}`);
        const data = await response.json();

        if (response.ok && data.success && data.has_history && data.initial_analysis) {
            restoreAnalysisView(data.initial_analysis, currentResumeText, data.messages || []);
            // Update local storage cache
            saveStateToLocal(jobId, data.initial_analysis, currentResumeText, data.messages || []);
        }
    } catch (e) {
        // Fall back gracefully to local storage
    }
}

async function resetAiResumeAnalyzer(isClearAndUploadNew) {
    const dropzone = document.getElementById('cpRaDropzone');
    const resultCard = document.getElementById('cpRaResultCard');
    const quickPrompts = document.getElementById('cpRaQuickPrompts');
    const messagesWin = document.getElementById('cpRaMessages');
    const errorAlert = document.getElementById('cpRaErrorAlert');
    const input = document.getElementById('cpRaInput');
    const sendBtn = document.getElementById('cpRaSendBtn');
    const fileInput = document.getElementById('cpRaFileInput');

    if (isClearAndUploadNew) {
        // Confirm before deleting
        const confirmDelete = window.confirm("Are you sure you want to delete this resume analysis and chat history for this job? You can then upload a new resume.");
        if (!confirmDelete) return;

        // 1. Delete from Server Database
        if (currentJobId) {
            try {
                await fetch('/api/v1/delete-resume-chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ job_id: currentJobId })
                });
            } catch (err) {
                console.warn('Error calling delete endpoint:', err);
            }
            // 2. Clear Local Storage
            clearStateFromLocal(currentJobId);
        }

        // 3. Clear In-Memory State
        chatHistory = [];
        currentResumeText = "";
        currentAnalysisData = null;

        if (fileInput) fileInput.value = "";
        if (messagesWin) messagesWin.innerHTML = "";
        if (resultCard) {
            resultCard.innerHTML = "";
            resultCard.classList.add('d-none');
        }
        if (quickPrompts) quickPrompts.classList.add('d-none');
        if (errorAlert) errorAlert.classList.add('d-none');

        if (input) {
            input.value = "";
            input.setAttribute('disabled', 'true');
        }
        if (sendBtn) sendBtn.setAttribute('disabled', 'true');

        if (dropzone) dropzone.classList.remove('d-none');
    } else {
        // Refresh assistant view / scroll to bottom
        if (messagesWin) messagesWin.scrollTop = messagesWin.scrollHeight;
        if (currentJobId) syncResumeChatHistory(currentJobId);
    }
}

async function processResumeFileUpload(file) {
    const dropzone = document.getElementById('cpRaDropzone');
    const progressWrap = document.getElementById('cpRaProgressWrap');
    const errorAlert = document.getElementById('cpRaErrorAlert');
    const resultCard = document.getElementById('cpRaResultCard');
    const quickPrompts = document.getElementById('cpRaQuickPrompts');
    const input = document.getElementById('cpRaInput');
    const sendBtn = document.getElementById('cpRaSendBtn');

    // Reset view
    errorAlert.classList.add('d-none');
    resultCard.classList.add('d-none');
    quickPrompts.classList.add('d-none');
    dropzone.classList.add('d-none');
    progressWrap.classList.remove('d-none');

    const formData = new FormData();
    formData.append('job_id', currentJobId);
    formData.append('resume_file', file);

    try {
        const response = await fetch('/api/v1/analyze-resume', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();
        progressWrap.classList.add('d-none');

        if (!response.ok || !data.success) {
            const errMsg = data.error || "Skills or structured experience not found in the uploaded file. Please upload a valid resume in PDF or image format.";
            document.getElementById('cpRaErrorMsg').innerText = errMsg;
            errorAlert.classList.remove('d-none');
            dropzone.classList.remove('d-none');
            return;
        }

        // Store resume text context for follow-up chat
        currentResumeText = data.resume_text_snippet || "";
        currentAnalysisData = data;
        
        // Render Result Card
        renderAnalysisResultCard(data);

        resultCard.classList.remove('d-none');
        quickPrompts.classList.remove('d-none');
        input.removeAttribute('disabled');
        sendBtn.removeAttribute('disabled');
        input.focus();

        // Save initial state to Local Storage
        saveStateToLocal(currentJobId, data, currentResumeText, []);

    } catch (err) {
        progressWrap.classList.add('d-none');
        dropzone.classList.remove('d-none');
        document.getElementById('cpRaErrorMsg').innerText = "An unexpected network error occurred while uploading. Please try again.";
        errorAlert.classList.remove('d-none');
    }
}

function formatAiMarkdown(rawText) {
    if (!rawText) return "";
    let text = rawText.trim();

    // 1. Clean up invalid combined raw markdown artifacts like "* ###" or "* **"
    text = text.replace(/^\s*\*\s*###\s+/gim, '### ');
    text = text.replace(/^\s*\*\s*####\s+/gim, '#### ');

    // 2. Format Headings with Theme Classes
    text = text.replace(/^### (.*$)/gim, '<h6 class="fw-bold mt-3 mb-2 cp-ra-md-h3">$1</h6>');
    text = text.replace(/^#### (.*$)/gim, '<strong class="d-block mt-2 mb-1 cp-ra-md-h4">$1</strong>');
    text = text.replace(/^## (.*$)/gim, '<h5 class="fw-bold mt-3 mb-2 cp-ra-md-h2">$1</h5>');

    // 3. Format Bullet Points
    text = text.replace(/^\s*[\*\-]\s+(.*$)/gim, '<li class="mb-1.5 ms-2 cp-ra-md-li">$1</li>');

    // 4. Bold **text**
    text = text.replace(/\*\*(.*?)\*\*/g, '<strong class="fw-bold cp-ra-md-bold">$1</strong>');

    // 5. Italic *text*
    text = text.replace(/\*(.*?)\*/g, '<em class="cp-ra-md-italic">$1</em>');

    // 6. Format Numbered Lists
    text = text.replace(/^(\d+)\.\s+(.*$)/gim, '<div class="ms-2 mb-1.5 cp-ra-md-num"><strong class="cp-ra-md-num-idx">$1.</strong> $2</div>');

    // 7. Line breaks
    text = text.replace(/\n/g, '<br>');

    return text;
}

function renderAnalysisResultCard(data) {
    const card = document.getElementById('cpRaResultCard');
    if (!card) return;
    
    // Badge Class
    let badgeClass = 'cp-ra-badge-orange';
    let iconStr = '⚡';
    if (data.badge_color === 'green') {
        badgeClass = 'cp-ra-badge-green';
        iconStr = '🟢';
    } else if (data.badge_color === 'red') {
        badgeClass = 'cp-ra-badge-red';
        iconStr = '🔴';
    }

    let formattedSummary = formatAiMarkdown(data.analysis_markdown);

    card.innerHTML = `
        <div class="d-flex align-items-center justify-content-between flex-wrap gap-2 mb-3 pb-2 border-bottom border-secondary border-opacity-25">
            <div>
                <small class="cp-ra-card-sublabel d-block" style="font-size: 0.78rem;">Composite Match Score</small>
                <h4 class="fw-bold cp-ra-card-score mb-0" style="font-size: 1.6rem;">${data.match_percentage}%</h4>
            </div>
            <div class="d-flex align-items-center gap-2">
                <span class="cp-ra-badge ${badgeClass}">
                    <span>${iconStr}</span>
                    <span>${data.badge_label}</span>
                </span>
            </div>
        </div>
        <div class="cp-ra-summary-body">
            ${formattedSummary}
        </div>
        <div class="cp-ra-disclaimer">
            <i class="bi bi-info-circle me-1"></i> ${data.disclaimer}
        </div>
    `;

    // Add initial summary to chat history
    chatHistory = [{
        role: "assistant",
        content: data.analysis_markdown
    }];
}

function sendQuickPrompt(promptText) {
    const input = document.getElementById('cpRaInput');
    if (!input) return;
    input.value = promptText;
    handleAiResumeChatSubmit(new Event('submit'));
}

async function handleAiResumeChatSubmit(event) {
    if (event) event.preventDefault();

    const input = document.getElementById('cpRaInput');
    const sendBtn = document.getElementById('cpRaSendBtn');
    const messagesWin = document.getElementById('cpRaMessages');

    const promptText = input.value.trim();
    if (!promptText) return;

    // Append User Message
    appendChatMessage('user', promptText);
    input.value = '';
    input.disabled = true;
    sendBtn.disabled = true;

    // Append Temporary Bot Loading Bubble
    const loadingId = 'loadingMsg_' + Date.now();
    appendLoadingMessage(loadingId);

    try {
        const response = await fetch('/api/v1/chat-resume', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                job_id: currentJobId,
                resume_text: currentResumeText,
                prompt: promptText,
                messages: chatHistory
            })
        });

        const data = await response.json();
        removeLoadingMessage(loadingId);

        if (response.ok && data.success) {
            appendChatMessage('assistant', data.reply);
            chatHistory.push({ role: 'user', content: promptText });
            chatHistory.push({ role: 'assistant', content: data.reply });

            // Persist updated conversation to Local Storage
            const followUpList = chatHistory.slice(1); // exclude initial result card
            saveStateToLocal(currentJobId, currentAnalysisData, currentResumeText, followUpList);
        } else {
            appendChatMessage('assistant', "⚠️ Sorry, I could not process your query at this moment. Please try again.");
        }

    } catch (err) {
        removeLoadingMessage(loadingId);
        appendChatMessage('assistant', "⚠️ Network connection error. Please check your internet connection.");
    } finally {
        input.disabled = false;
        sendBtn.disabled = false;
        input.focus();
    }
}

function appendChatMessage(role, text) {
    const messagesWin = document.getElementById('cpRaMessages');
    if (!messagesWin) return;
    const isUser = role === 'user';
    const msgDiv = document.createElement('div');
    msgDiv.className = `cp-ra-msg ${isUser ? 'cp-ra-msg-user' : 'cp-ra-msg-bot'}`;

    const formattedText = formatAiMarkdown(text);

    msgDiv.innerHTML = `
        <div class="cp-ra-bubble">
            ${formattedText}
        </div>
    `;

    messagesWin.appendChild(msgDiv);
    messagesWin.scrollTop = messagesWin.scrollHeight;
}

function appendLoadingMessage(id) {
    const messagesWin = document.getElementById('cpRaMessages');
    if (!messagesWin) return;
    const msgDiv = document.createElement('div');
    msgDiv.id = id;
    msgDiv.className = 'cp-ra-msg cp-ra-msg-bot';
    msgDiv.innerHTML = `
        <div class="cp-ra-bubble text-pearl italic">
            <span class="spinner-border spinner-border-sm me-2" role="status"></span> Analyzing...
        </div>
    `;
    messagesWin.appendChild(msgDiv);
    messagesWin.scrollTop = messagesWin.scrollHeight;
}

function removeLoadingMessage(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
}

// Check on initial page load if drawer is on page
document.addEventListener('DOMContentLoaded', () => {
    const drawer = document.getElementById('cpRaDrawer');
    if (drawer) {
        const jId = drawer.getAttribute('data-job-id');
        if (jId) {
            currentJobId = jId;
            // Pre-check if local history exists
            const localState = loadStateFromLocal(jId);
            if (localState && localState.analysisData) {
                restoreAnalysisView(localState.analysisData, localState.resumeText, localState.messages);
            }
        }
    }
});

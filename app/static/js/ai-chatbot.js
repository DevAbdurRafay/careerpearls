(function () {
    let abortController = null;
    let chatHistory = [];

    const AI_AVATAR_SVG = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="10" rx="2"></rect><circle cx="12" cy="5" r="2"></circle><path d="M12 7v4"></path></svg>`;
    function getUserStorageKey() {
        const container = document.getElementById('cpAiChatContainer');
        if (container) {
            const userId = container.getAttribute('data-user-id') || 'guest';
            const userEmail = container.getAttribute('data-user-email') || 'guest';
            const userRole = container.getAttribute('data-user-role') || 'guest';
            if (userId !== 'guest' && userEmail !== 'guest') {
                const cleanEmail = String(userEmail).trim().toLowerCase().replace(/[^a-z0-9_@.-]/g, '_');
                return `cp_ai_chats_${userRole}_u${userId}_${cleanEmail}`;
            }
        }
        return 'cp_ai_chats_guest';
    }

    function escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function formatMarkdown(text) {
        if (!text) return '';
        let formatted = escapeHtml(text);

        // 1. Convert markdown headings with optional leading bullets/hashes like "* ### Heading" or "### Heading"
        formatted = formatted.replace(/^(?:\*\s*)?(?:#{1,6})\s*(.*?)$/gm, '<div class="fw-bold cp-ai-heading mt-2.5 mb-1 fs-6">$1</div>');

        // 2. Bold: **text**
        formatted = formatted.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        
        // 3. Italic: *text*
        formatted = formatted.replace(/(?<!^\s*)\*([^\*\n]+)\*/gm, '<em>$1</em>');

        // 4. Code blocks: ```code```
        formatted = formatted.replace(/```([\s\S]*?)```/g, '<pre class="my-2 p-2 rounded bg-dark text-light"><code>$1</code></pre>');
        // Inline code: `code`
        formatted = formatted.replace(/`([^`]+)`/g, '<code class="px-1 py-0.5 rounded bg-dark text-info">$1</code>');

        // 5. Line breaks & bullet points parsing
        const lines = formatted.split('\n');
        let html = '';
        let inList = false;

        lines.forEach(line => {
            let trimmed = line.trim();
            if (!trimmed) return;

            // Clean up orphan * or # at start of line if any remained
            trimmed = trimmed.replace(/^[\*\#]\s+/, '');

            if (trimmed.startsWith('• ') || trimmed.startsWith('- ') || line.trim().startsWith('* ')) {
                if (!inList) {
                    html += '<ul class="mb-2 ps-3">';
                    inList = true;
                }
                let itemContent = trimmed;
                if (itemContent.startsWith('• ') || itemContent.startsWith('- ')) {
                    itemContent = itemContent.substring(2);
                } else if (itemContent.startsWith('* ')) {
                    itemContent = itemContent.substring(2);
                }
                html += `<li>${itemContent}</li>`;
            } else {
                if (inList) {
                    html += '</ul>';
                    inList = false;
                }
                if (trimmed.startsWith('<div class="fw-bold') || trimmed.startsWith('<pre') || trimmed.startsWith('<ul')) {
                    html += trimmed;
                } else {
                    html += `<p class="mb-1.5">${trimmed}</p>`;
                }
            }
        });
        if (inList) html += '</ul>';

        // 6. Links conversion
        html = html.replace(/(\/(?:explore|complaint|candidate\/[a-z0-9\-]+|employer\/[a-z0-9\-]+|terms-of-service|privacy-policy|about))/g, '<a href="$1" class="text-info fw-semibold text-decoration-underline">$1</a>');

        return html;
    }

    function initAiChatbot() {
        const triggerBtn = document.getElementById('cpAiTriggerBtn');
        const drawer = document.getElementById('cpAiDrawer');
        const backdrop = document.getElementById('cpAiDrawerBackdrop');
        const closeBtn = document.getElementById('cpAiCloseDrawer');
        const refreshBtn = document.getElementById('cpAiRefreshBtn');
        const clearBtn = document.getElementById('cpAiClearChat');
        const confirmOverlay = document.getElementById('cpAiConfirmOverlay');
        const confirmYes = document.getElementById('cpAiConfirmYes');
        const confirmNo = document.getElementById('cpAiConfirmNo');
        const form = document.getElementById('cpAiChatForm');
        const input = document.getElementById('cpAiInput');
        const messagesWrap = document.getElementById('cpAiMessages');
        const stopBar = document.getElementById('cpAiStopBar');
        const stopBtn = document.getElementById('cpAiStopBtn');
        const charCount = document.getElementById('cpAiCharCount');
        const sendBtn = document.getElementById('cpAiSendBtn');

        if (!triggerBtn || !drawer) return;

        const defaultWelcomeHtml = messagesWrap ? messagesWrap.innerHTML : '';

        function saveChatToStorage() {
            try {
                if (!messagesWrap) return;
                const storageKey = getUserStorageKey();
                const data = {
                    chatHistory: chatHistory,
                    htmlMessages: messagesWrap.innerHTML
                };
                localStorage.setItem(storageKey, JSON.stringify(data));
            } catch (e) {
                console.error('Error saving chat history to localStorage:', e);
            }
        }

        function loadChatFromStorage() {
            try {
                if (!messagesWrap) return false;
                // Clear legacy non-isolated shared keys to prevent cross-account leak
                try {
                    localStorage.removeItem('cp_ai_chat_history_v2');
                    localStorage.removeItem('cp_ai_chat_history');
                    localStorage.removeItem('cp_ai_chat_history_v1');
                } catch (e) {}

                const storageKey = getUserStorageKey();
                const raw = localStorage.getItem(storageKey);
                if (raw) {
                    const parsed = JSON.parse(raw);
                    if (parsed && Array.isArray(parsed.chatHistory) && parsed.chatHistory.length > 0) {
                        chatHistory = parsed.chatHistory;
                        if (parsed.htmlMessages) {
                            messagesWrap.innerHTML = parsed.htmlMessages;
                            messagesWrap.scrollTop = messagesWrap.scrollHeight;
                            return true;
                        }
                    }
                }
            } catch (e) {
                console.error('Error loading chat history from localStorage:', e);
            }
            return false;
        }

        // Restore saved chat history on load
        loadChatFromStorage();

        function openDrawer() {
            drawer.classList.add('open');
            if (backdrop) {
                backdrop.classList.remove('d-none');
                setTimeout(() => backdrop.classList.add('show'), 10);
            }
            if (input) input.focus();
            if (messagesWrap) messagesWrap.scrollTop = messagesWrap.scrollHeight;
        }

        function closeDrawer() {
            drawer.classList.remove('open');
            if (backdrop) {
                backdrop.classList.remove('show');
                setTimeout(() => backdrop.classList.add('d-none'), 250);
            }
            if (confirmOverlay) confirmOverlay.classList.add('d-none');
        }

        triggerBtn.addEventListener('click', openDrawer);
        if (closeBtn) closeBtn.addEventListener('click', closeDrawer);
        if (backdrop) backdrop.addEventListener('click', closeDrawer);

        // Escape key to close
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && drawer.classList.contains('open')) {
                if (confirmOverlay && !confirmOverlay.classList.contains('d-none')) {
                    confirmOverlay.classList.add('d-none');
                } else {
                    closeDrawer();
                }
            }
        });

        // Refresh view button handler
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => {
                if (messagesWrap) messagesWrap.scrollTop = messagesWrap.scrollHeight;
            });
        }

        // Dustbin Clear Chat Button Handler -> Opens Confirmation Modal
        if (clearBtn) {
            clearBtn.addEventListener('click', () => {
                if (confirmOverlay) {
                    confirmOverlay.classList.remove('d-none');
                }
            });
        }

        // Confirmation Modal: "No, Keep"
        if (confirmNo) {
            confirmNo.addEventListener('click', () => {
                if (confirmOverlay) confirmOverlay.classList.add('d-none');
            });
        }

        // Confirmation Modal: "Yes, Clear"
        if (confirmYes) {
            confirmYes.addEventListener('click', () => {
                chatHistory = [];
                try {
                    const storageKey = getUserStorageKey();
                    localStorage.removeItem(storageKey);
                } catch (e) {}

                if (messagesWrap) {
                    messagesWrap.innerHTML = defaultWelcomeHtml || `
                        <div class="cp-ai-msg cp-ai-msg-assistant">
                            <div class="cp-ai-msg-avatar">${AI_AVATAR_SVG}</div>
                            <div class="cp-ai-msg-bubble">
                                <p class="mb-1 fw-semibold">Chat session reset! 🗑️</p>
                                <p class="mb-0">How can I assist you with your career or recruitment today?</p>
                            </div>
                        </div>
                    `;
                }
                if (confirmOverlay) confirmOverlay.classList.add('d-none');
            });
        }

        // Auto-resize input & char counter
        if (input) {
            input.addEventListener('input', () => {
                input.style.height = 'auto';
                input.style.height = (input.scrollHeight) + 'px';
                if (charCount) {
                    charCount.textContent = `${input.value.length}/1500`;
                }
            });

            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    form.dispatchEvent(new Event('submit'));
                }
            });
        }

        // Quick prompt chips horizontal mouse wheel scrolling
        const chipsScroll = drawer.querySelector('.cp-ai-chips-scroll');
        if (chipsScroll) {
            chipsScroll.addEventListener('wheel', (e) => {
                if (e.deltaY !== 0) {
                    e.preventDefault();
                    chipsScroll.scrollLeft += e.deltaY;
                }
            }, { passive: false });
        }

        // Quick prompt chips click listener - loads prompt into input bar without auto-executing
        document.querySelectorAll('.cp-ai-chip').forEach(chip => {
            chip.addEventListener('click', () => {
                const prompt = chip.getAttribute('data-prompt');
                if (prompt && input) {
                    input.value = prompt;
                    input.style.height = 'auto';
                    input.style.height = (input.scrollHeight) + 'px';
                    if (charCount) {
                        charCount.textContent = `${input.value.length}/1500`;
                    }
                    openDrawer();
                    input.focus();
                }
            });
        });

        function appendMessage(role, text) {
            const msgDiv = document.createElement('div');
            msgDiv.className = `cp-ai-msg cp-ai-msg-${role}`;

            if (role === 'user') {
                msgDiv.innerHTML = `
                    <div class="cp-ai-msg-bubble">
                        <p class="mb-0">${escapeHtml(text)}</p>
                    </div>
                `;
            } else {
                msgDiv.innerHTML = `
                    <div class="cp-ai-msg-avatar">${AI_AVATAR_SVG}</div>
                    <div class="cp-ai-msg-bubble">
                        ${formatMarkdown(text)}
                    </div>
                `;
            }

            messagesWrap.appendChild(msgDiv);
            messagesWrap.scrollTop = messagesWrap.scrollHeight;
            saveChatToStorage();
            return msgDiv;
        }

        function showTypingIndicator() {
            const typingDiv = document.createElement('div');
            typingDiv.className = 'cp-ai-msg cp-ai-msg-assistant cp-ai-typing';
            typingDiv.id = 'cpAiTypingIndicator';
            typingDiv.innerHTML = `
                <div class="cp-ai-msg-avatar">${AI_AVATAR_SVG}</div>
                <div class="cp-ai-msg-bubble d-flex align-items-center gap-1.5 py-2 px-3">
                    <span class="spinner-grow spinner-grow-sm text-info" style="width: 8px; height: 8px;"></span>
                    <span class="spinner-grow spinner-grow-sm text-info" style="width: 8px; height: 8px; animation-delay: 0.15s;"></span>
                    <span class="spinner-grow spinner-grow-sm text-info" style="width: 8px; height: 8px; animation-delay: 0.3s;"></span>
                    <small class="ms-1 text-pearl-muted fst-italic">Thinking...</small>
                </div>
            `;
            messagesWrap.appendChild(typingDiv);
            messagesWrap.scrollTop = messagesWrap.scrollHeight;
        }

        function removeTypingIndicator() {
            const el = document.getElementById('cpAiTypingIndicator');
            if (el) el.remove();
        }

        // Stop generation handler
        if (stopBtn) {
            stopBtn.addEventListener('click', () => {
                if (abortController) {
                    abortController.abort();
                    abortController = null;
                }
                removeTypingIndicator();
                stopBar.classList.add('d-none');
                if (sendBtn) sendBtn.disabled = false;
                appendMessage('assistant', '_Generation stopped by user._');
            });
        }

        // Submit form
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const text = input.value.trim();
            if (!text) return;

            appendMessage('user', text);
            chatHistory.push({ role: 'user', content: text });
            input.value = '';
            input.style.height = 'auto';
            if (charCount) charCount.textContent = '0/1500';

            showTypingIndicator();
            if (stopBar) stopBar.classList.remove('d-none');
            if (sendBtn) sendBtn.disabled = true;

            abortController = new AbortController();

            try {
                const csrfTokenMeta = document.querySelector('meta[name="csrf-token"]');
                const csrfToken = csrfTokenMeta ? csrfTokenMeta.getAttribute('content') : '';

                const resp = await fetch('/api/ai/chat', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrfToken
                    },
                    body: JSON.stringify({ messages: chatHistory }),
                    signal: abortController.signal
                });

                removeTypingIndicator();
                if (stopBar) stopBar.classList.add('d-none');
                if (sendBtn) sendBtn.disabled = true;

                const data = await resp.json();
                if (data && data.reply) {
                    appendMessage('assistant', data.reply);
                    chatHistory.push({ role: 'assistant', content: data.reply });
                    saveChatToStorage();
                } else {
                    appendMessage('assistant', data.error || '⚠️ The AI Assistant could not process your message. Please try again.');
                }
            } catch (err) {
                removeTypingIndicator();
                if (stopBar) stopBar.classList.add('d-none');
                if (sendBtn) sendBtn.disabled = false;

                if (err.name === 'AbortError') {
                    console.log('AI Generation aborted by user.');
                } else {
                    console.error('AI Chatbot error:', err);
                    appendMessage('assistant', '⚠️ Network or server error. Please check your connection and try again.');
                }
            } finally {
                abortController = null;
                if (sendBtn) sendBtn.disabled = false;
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initAiChatbot);
    } else {
        initAiChatbot();
    }
})();

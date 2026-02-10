/**
 * Gideon Admin Dashboard - Main Application
 */
(function () {
    'use strict';

    // ── State ────────────────────────────────────────────────
    let authToken = null;
    let ws = null;
    let wsReconnectTimer = null;
    const WS_RECONNECT_DELAY = 3000;

    // Model cache: { provider: [model_ids] }
    var modelCache = {};

    // Messages state
    var msgCurrentPage = 1;
    var msgTotalPages = 1;
    var msgSources = null; // cached sources data

    // ── Helpers ──────────────────────────────────────────────

    async function api(method, path, body) {
        const opts = {
            method,
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
        };
        if (authToken) {
            opts.headers['Authorization'] = 'Bearer ' + authToken;
        }
        if (body !== undefined) {
            opts.body = JSON.stringify(body);
        }
        const res = await fetch(path, opts);
        if (res.status === 401) {
            handleLogout();
            throw new Error('Session expired');
        }
        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.error || 'Request failed');
        }
        return data;
    }

    function $(selector) {
        return document.querySelector(selector);
    }

    function $$(selector) {
        return document.querySelectorAll(selector);
    }

    function formatUptime(seconds) {
        const d = Math.floor(seconds / 86400);
        const h = Math.floor((seconds % 86400) / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        if (d > 0) return d + 'd ' + h + 'h';
        if (h > 0) return h + 'h ' + m + 'm';
        return m + 'm';
    }

    function formatBytes(bytes) {
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / 1048576).toFixed(1) + ' MB';
    }

    function formatTime(date) {
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    }

    function formatDateTime(str) {
        if (!str) return 'N/A';
        var d = new Date(str);
        if (isNaN(d.getTime())) return str;
        return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }

    function escapeHtml(str) {
        if (!str) return '';
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    function showSaveStatus(elementId, message, isError) {
        const el = document.getElementById(elementId);
        if (!el) return;
        el.textContent = message;
        el.className = 'save-status ' + (isError ? 'error' : 'success');
        setTimeout(function() { el.textContent = ''; }, 4000);
    }

    // ── Model Select Helpers ─────────────────────────────────

    async function fetchModels(provider) {
        if (modelCache[provider]) return modelCache[provider];
        try {
            var models = await api('GET', '/api/models/' + provider);
            modelCache[provider] = models;
            return models;
        } catch (e) {
            console.error('Failed to fetch models for ' + provider + ':', e);
            return [];
        }
    }

    function populateModelSelect(selectEl, models, currentValue, emptyLabel) {
        var html = '';
        if (emptyLabel) {
            html += '<option value="">' + escapeHtml(emptyLabel) + '</option>';
        }
        models.forEach(function(model) {
            var selected = (model === currentValue) ? ' selected' : '';
            var label = model;
            if (model === currentValue) {
                label = '> ' + model + ' (current)';
            }
            html += '<option value="' + escapeHtml(model) + '"' + selected + '>' + escapeHtml(label) + '</option>';
        });
        selectEl.innerHTML = html;
    }

    function setupModelSearch(searchId, selectId) {
        var searchEl = document.getElementById(searchId);
        var selectEl = document.getElementById(selectId);
        if (!searchEl || !selectEl) return;

        searchEl.addEventListener('input', function() {
            var filter = searchEl.value.toLowerCase();
            var options = selectEl.options;
            for (var i = 0; i < options.length; i++) {
                var text = options[i].value.toLowerCase() + ' ' + options[i].textContent.toLowerCase();
                options[i].style.display = (!filter || text.indexOf(filter) !== -1) ? '' : 'none';
            }
        });
    }

    async function loadModelsForProvider(provider, selectId, currentValue, emptyLabel) {
        var selectEl = document.getElementById(selectId);
        if (!selectEl) return;
        selectEl.innerHTML = '<option value="">Loading models...</option>';
        var models = await fetchModels(provider);
        populateModelSelect(selectEl, models, currentValue, emptyLabel);
    }

    // ── Auth ─────────────────────────────────────────────────

    async function checkAuth() {
        try {
            const data = await api('GET', '/api/auth/check');
            if (data.authenticated) {
                // Restore token from cookie-based session so WebSocket can authenticate
                if (data.token) {
                    authToken = data.token;
                }
                showDashboard();
                return;
            }
        } catch (e) {
            // Not authenticated
        }
        showLogin();
    }

    function showLogin() {
        $('#login-screen').style.display = 'flex';
        $('#dashboard').style.display = 'none';
        disconnectWs();
    }

    function showDashboard() {
        $('#login-screen').style.display = 'none';
        $('#dashboard').style.display = 'flex';
        loadOverview();
        connectWs();
    }

    function handleLogout() {
        authToken = null;
        api('POST', '/api/auth/logout').catch(function() {});
        showLogin();
    }

    // ── Tab Navigation ───────────────────────────────────────

    function switchTab(tabName) {
        $$('.nav-item').forEach(function(item) {
            item.classList.toggle('active', item.dataset.tab === tabName);
        });
        $$('.tab-content').forEach(function(tab) {
            tab.classList.toggle('active', tab.id === 'tab-' + tabName);
        });

        // Load data for the tab
        switch (tabName) {
            case 'overview': loadOverview(); break;
            case 'settings': loadSettings(); break;
            case 'channels': loadChannels(); break;
            case 'threads': loadThreads(); break;
            case 'image-gen': loadImageSettings(); break;
            case 'messages': loadMessageSources(); break;
            case 'diagnostics': break;
            case 'activity': break;
        }
    }

    // ── Overview ─────────────────────────────────────────────

    async function loadOverview() {
        try {
            const data = await api('GET', '/api/overview');
            $('#stat-guilds').textContent = data.guilds;
            $('#stat-messages').textContent = data.message_count >= 0 ? data.message_count : 'N/A';
            $('#stat-threads').textContent = data.thread_count >= 0 ? data.thread_count : 'N/A';
            $('#stat-channels').textContent = data.channel_config_count;
            $('#stat-latency').textContent = data.latency_ms !== null ? data.latency_ms : 'N/A';
            $('#stat-uptime').textContent = formatUptime(data.uptime_seconds);
            $('#info-bot-name').textContent = data.bot_name;
            $('#info-bot-id').textContent = data.bot_id;
            $('#info-model').textContent = data.global_model;
            $('#info-provider').textContent = data.global_provider;
            $('#info-db-size').textContent = formatBytes(data.database_size_bytes);

            var badge = $('#bot-status-badge');
            badge.textContent = 'Online';
            badge.className = 'badge badge-success';
        } catch (e) {
            console.error('Failed to load overview:', e);
        }
    }

    // ── Settings ─────────────────────────────────────────────

    async function loadSettings() {
        try {
            const data = await api('GET', '/api/settings');
            var provider = data.global_provider || 'openrouter';

            $('#setting-provider').value = provider;
            $('#setting-memory').value = data.max_channel_history || 35;
            $('#setting-window').value = data.time_window_hours || 48;
            $('#setting-prune').value = data.prune_frequency_hours || 24;
            $('#setting-system-prompt').value = data.global_system_prompt || '';

            await loadModelsForProvider(provider, 'setting-model', data.global_model, null);

            var searchEl = document.getElementById('setting-model-search');
            if (searchEl) searchEl.value = '';

            const intent = await api('GET', '/api/settings/intent');
            $('#intent-enabled').value = intent.enabled ? 'true' : 'false';
            $('#intent-threshold').value = intent.threshold !== undefined ? intent.threshold : 0.7;

            await loadModelsForProvider(provider, 'intent-model', intent.model, null);
            var intentSearchEl = document.getElementById('intent-model-search');
            if (intentSearchEl) intentSearchEl.value = '';
        } catch (e) {
            console.error('Failed to load settings:', e);
        }
    }

    async function saveSettings(e) {
        e.preventDefault();
        try {
            await api('PUT', '/api/settings', {
                global_provider: $('#setting-provider').value,
                global_model: $('#setting-model').value,
                max_channel_history: parseInt($('#setting-memory').value),
                time_window_hours: parseInt($('#setting-window').value),
                prune_frequency_hours: parseInt($('#setting-prune').value),
                global_system_prompt: $('#setting-system-prompt').value || null,
            });
            showSaveStatus('settings-save-status', 'Settings saved', false);
        } catch (e) {
            showSaveStatus('settings-save-status', 'Error: ' + e.message, true);
        }
    }

    async function saveIntentSettings(e) {
        e.preventDefault();
        try {
            await api('PUT', '/api/settings/intent', {
                enabled: $('#intent-enabled').value === 'true',
                model: $('#intent-model').value,
                threshold: parseFloat($('#intent-threshold').value),
            });
            showSaveStatus('intent-save-status', 'Intent settings saved', false);
        } catch (e) {
            showSaveStatus('intent-save-status', 'Error: ' + e.message, true);
        }
    }

    async function onProviderChange() {
        var provider = $('#setting-provider').value;
        delete modelCache[provider];
        await loadModelsForProvider(provider, 'setting-model', null, null);
        await loadModelsForProvider(provider, 'intent-model', null, null);
    }

    // ── Channels ─────────────────────────────────────────────

    async function loadChannels() {
        var container = $('#channels-list');
        try {
            const channels = await api('GET', '/api/channels');
            if (channels.length === 0) {
                container.innerHTML = '<div class="empty-state">No channels with custom configurations.</div>';
                return;
            }

            var html = '<table class="data-table"><thead><tr>' +
                '<th>Channel</th><th>Server</th><th>Model</th><th>Provider</th><th>Actions</th>' +
                '</tr></thead><tbody>';

            channels.forEach(function(ch) {
                html += '<tr>' +
                    '<td>' + escapeHtml(ch.channel_name || ch.channel_id) + '</td>' +
                    '<td>' + escapeHtml(ch.guild_name || 'Unknown') + '</td>' +
                    '<td>' + (ch.model ? '<span class="code">' + escapeHtml(ch.model) + '</span>' : '<span class="text-muted">Global</span>') + '</td>' +
                    '<td>' + (ch.provider ? escapeHtml(ch.provider) : '<span class="text-muted">Global</span>') + '</td>' +
                    '<td><button class="btn btn-small btn-secondary" onclick="window._editChannel(\'' + escapeHtml(ch.channel_id) + '\')">Edit</button></td>' +
                    '</tr>';
            });

            html += '</tbody></table>';
            container.innerHTML = html;
        } catch (e) {
            container.innerHTML = '<div class="empty-state">Error loading channels: ' + escapeHtml(e.message) + '</div>';
        }
    }

    async function editChannel(channelId) {
        try {
            const data = await api('GET', '/api/channels/' + channelId);
            $('#channel-edit-id').value = channelId;
            $('#channel-modal-name').textContent = data.channel_name || channelId;
            $('#channel-edit-provider').value = data.provider || '';
            $('#channel-edit-prompt').value = data.system_prompt || '';

            var settings = await api('GET', '/api/settings');
            var provider = data.provider || settings.global_provider || 'openrouter';
            await loadModelsForProvider(provider, 'channel-edit-model', data.model, 'Use Global Default');

            var searchEl = document.getElementById('channel-model-search');
            if (searchEl) searchEl.value = '';

            $('#channel-modal').style.display = 'flex';
        } catch (e) {
            alert('Error loading channel: ' + e.message);
        }
    }
    window._editChannel = editChannel;

    async function saveChannel(e) {
        e.preventDefault();
        var channelId = $('#channel-edit-id').value;
        try {
            await api('PUT', '/api/channels/' + channelId, {
                model: $('#channel-edit-model').value || null,
                provider: $('#channel-edit-provider').value || undefined,
                system_prompt: $('#channel-edit-prompt').value || null,
            });
            $('#channel-modal').style.display = 'none';
            loadChannels();
        } catch (e) {
            alert('Error saving channel: ' + e.message);
        }
    }

    async function resetChannel() {
        var channelId = $('#channel-edit-id').value;
        if (!confirm('Reset this channel to global defaults?')) return;
        try {
            await api('DELETE', '/api/channels/' + channelId);
            $('#channel-modal').style.display = 'none';
            loadChannels();
        } catch (e) {
            alert('Error resetting channel: ' + e.message);
        }
    }

    // ── Threads ──────────────────────────────────────────────

    async function loadThreads() {
        var container = $('#threads-list');
        try {
            const threads = await api('GET', '/api/threads');
            if (threads.length === 0) {
                container.innerHTML = '<div class="empty-state">No active threads.</div>';
                return;
            }

            var html = '<table class="data-table"><thead><tr>' +
                '<th>Name</th><th>Channel</th><th>Messages</th><th>Model</th><th>Created</th><th>Actions</th>' +
                '</tr></thead><tbody>';

            threads.forEach(function(t) {
                var created = t.created_at ? new Date(t.created_at).toLocaleDateString() : 'N/A';
                html += '<tr>' +
                    '<td>' + escapeHtml(t.name || 'Unnamed') + '</td>' +
                    '<td>' + escapeHtml(t.channel_id) + '</td>' +
                    '<td>' + (t.message_count || 0) + '</td>' +
                    '<td>' + (t.model ? '<span class="code">' + escapeHtml(t.model) + '</span>' : '<span class="text-muted">Default</span>') + '</td>' +
                    '<td>' + created + '</td>' +
                    '<td><button class="btn btn-small btn-secondary" onclick="window._editThread(\'' + escapeHtml(t.thread_id) + '\')">Edit</button></td>' +
                    '</tr>';
            });

            html += '</tbody></table>';
            container.innerHTML = html;
        } catch (e) {
            container.innerHTML = '<div class="empty-state">Error loading threads: ' + escapeHtml(e.message) + '</div>';
        }
    }

    async function editThread(threadId) {
        try {
            const data = await api('GET', '/api/threads/' + threadId);
            $('#thread-edit-id').value = threadId;
            $('#thread-modal-name').textContent = data.name || threadId;
            $('#thread-edit-name').value = data.name || '';
            $('#thread-edit-prompt').value = data.system_prompt || '';

            var settings = await api('GET', '/api/settings');
            var provider = settings.global_provider || 'openrouter';
            await loadModelsForProvider(provider, 'thread-edit-model', data.model, 'Use Channel/Global Default');

            var searchEl = document.getElementById('thread-model-search');
            if (searchEl) searchEl.value = '';

            $('#thread-modal').style.display = 'flex';
        } catch (e) {
            alert('Error loading thread: ' + e.message);
        }
    }
    window._editThread = editThread;

    async function saveThread(e) {
        e.preventDefault();
        var threadId = $('#thread-edit-id').value;
        try {
            await api('PUT', '/api/threads/' + threadId, {
                name: $('#thread-edit-name').value,
                model: $('#thread-edit-model').value || null,
                system_prompt: $('#thread-edit-prompt').value || null,
            });
            $('#thread-modal').style.display = 'none';
            loadThreads();
        } catch (e) {
            alert('Error saving thread: ' + e.message);
        }
    }

    async function deleteThread() {
        var threadId = $('#thread-edit-id').value;
        if (!confirm('Delete this thread and all its messages? This cannot be undone.')) return;
        try {
            await api('DELETE', '/api/threads/' + threadId);
            $('#thread-modal').style.display = 'none';
            loadThreads();
        } catch (e) {
            alert('Error deleting thread: ' + e.message);
        }
    }

    // ── Messages ─────────────────────────────────────────────

    async function loadMessageSources() {
        if (msgSources) return; // Already loaded
        try {
            msgSources = await api('GET', '/api/messages/sources');
        } catch (e) {
            console.error('Failed to load message sources:', e);
        }
    }

    function onSourceTypeChange() {
        var type = $('#msg-source-type').value;
        var group = $('#msg-source-select-group');
        var sel = $('#msg-source-id');

        if (type === 'all') {
            group.style.display = 'none';
            return;
        }

        group.style.display = '';
        sel.innerHTML = '<option value="">Loading...</option>';

        if (!msgSources) {
            loadMessageSources().then(function() { populateSourceSelect(type); });
        } else {
            populateSourceSelect(type);
        }
    }

    function populateSourceSelect(type) {
        var sel = $('#msg-source-id');
        var html = '';

        if (type === 'channel' && msgSources && msgSources.channels) {
            msgSources.channels.forEach(function(ch) {
                var label = (ch.name || ch.id);
                if (ch.guild) label += ' (' + ch.guild + ')';
                label += ' - ' + ch.message_count + ' msgs';
                html += '<option value="' + escapeHtml(ch.id) + '">' + escapeHtml(label) + '</option>';
            });
        } else if (type === 'thread' && msgSources && msgSources.threads) {
            msgSources.threads.forEach(function(t) {
                var label = (t.name || t.id) + ' - ' + t.message_count + ' msgs';
                html += '<option value="' + escapeHtml(t.id) + '">' + escapeHtml(label) + '</option>';
            });
        }

        if (!html) {
            html = '<option value="">No ' + type + 's with messages</option>';
        }
        sel.innerHTML = html;
    }

    async function loadMessages(page) {
        if (!page) page = 1;
        msgCurrentPage = page;

        var container = $('#messages-container');
        container.innerHTML = '<div class="loading-text">Loading messages...</div>';

        var params = 'page=' + page + '&per_page=50';

        var sourceType = $('#msg-source-type').value;
        var sourceId = $('#msg-source-id').value;

        if (sourceType === 'channel' && sourceId) {
            params += '&channel_id=' + encodeURIComponent(sourceId);
        } else if (sourceType === 'thread' && sourceId) {
            params += '&thread_id=' + encodeURIComponent(sourceId);
        }

        var roleFilter = $('#msg-role-filter').value;
        if (roleFilter) {
            params += '&role=' + encodeURIComponent(roleFilter);
        }

        try {
            var data = await api('GET', '/api/messages?' + params);
            msgTotalPages = data.total_pages;

            if (data.messages.length === 0) {
                container.innerHTML = '<div class="empty-state">No messages found.</div>';
                $('#messages-pagination').style.display = 'none';
                return;
            }

            var html = '';
            data.messages.forEach(function(msg) {
                var roleClass = 'msg-role-' + (msg.role || 'user');
                var roleBadge = msg.role || 'unknown';
                var timeStr = formatDateTime(msg.timestamp);
                var channelInfo = '';
                if (msg.channel_name) {
                    channelInfo = '#' + msg.channel_name;
                } else if (msg.channel_id) {
                    channelInfo = '#' + msg.channel_id;
                } else if (msg.thread_id) {
                    channelInfo = 'Thread ' + msg.thread_id;
                }

                var content = msg.content || '';

                // Check for image markers: [image:url] or [image:attachment]
                var imageHtml = '';
                var imageMatch = content.match(/^\[image:(.*?)\]\s*/);
                if (imageMatch) {
                    var imageRef = imageMatch[1];
                    content = content.substring(imageMatch[0].length);
                    if (imageRef && imageRef !== 'attachment' && imageRef.startsWith('http')) {
                        imageHtml = '<div class="msg-image"><a href="' + escapeHtml(imageRef) + '" target="_blank" rel="noopener"><img src="' + escapeHtml(imageRef) + '" alt="Generated image" loading="lazy"></a></div>';
                    } else {
                        imageHtml = '<div class="msg-image-placeholder">Generated image (attachment - not available in dashboard)</div>';
                    }
                }

                // Check for failed generation marker
                var isFailedGen = content.startsWith('[image generation failed]');
                if (isFailedGen) {
                    content = content.substring('[image generation failed] '.length);
                }

                // Truncate very long messages for display
                var truncated = false;
                if (content.length > 1000) {
                    content = content.substring(0, 1000);
                    truncated = true;
                }

                html += '<div class="msg-bubble ' + roleClass + '">';
                html += '<div class="msg-header">';
                html += '<span class="msg-role-badge ' + roleClass + '">' + escapeHtml(roleBadge) + '</span>';
                if (msg.user_id) {
                    html += '<span class="msg-user">' + escapeHtml(msg.user_id) + '</span>';
                }
                if (channelInfo) {
                    html += '<span class="msg-channel">' + escapeHtml(channelInfo) + '</span>';
                }
                html += '<span class="msg-time">' + escapeHtml(timeStr) + '</span>';
                html += '</div>';
                html += '<div class="msg-content">' + escapeHtml(content);
                if (truncated) {
                    html += '<span class="msg-truncated">... (truncated)</span>';
                }
                html += '</div>';
                if (imageHtml) {
                    html += imageHtml;
                }
                html += '</div>';
            });

            container.innerHTML = html;

            // Update pagination
            var pagination = $('#messages-pagination');
            pagination.style.display = 'flex';
            $('#msg-page-info').textContent = 'Page ' + data.page + ' of ' + data.total_pages + ' (' + data.total + ' messages)';
            $('#msg-prev').disabled = (data.page <= 1);
            $('#msg-next').disabled = (data.page >= data.total_pages);

        } catch (e) {
            container.innerHTML = '<div class="empty-state">Error loading messages: ' + escapeHtml(e.message) + '</div>';
            $('#messages-pagination').style.display = 'none';
        }
    }

    // ── Diagnostics ──────────────────────────────────────────

    async function runDiagnostics() {
        var container = $('#diagnostics-results');
        container.innerHTML = '<p class="loading-text">Running diagnostics...</p>';

        try {
            const data = await api('GET', '/api/diagnostics');
            var html = '';

            html += '<div class="diag-section"><h4>Bot Status</h4>';
            html += diagItem('Status', statusDot(data.bot_status === 'online' ? 'ok' : 'warn') + ' ' + data.bot_status);
            html += diagItem('Latency', data.latency_ms !== null ? data.latency_ms + ' ms' : 'N/A');
            html += diagItem('Servers', data.guilds);
            html += diagItem('Uptime', formatUptime(data.uptime_seconds));
            html += '</div>';

            if (data.database) {
                html += '<div class="diag-section"><h4>Database</h4>';
                html += diagItem('Status', statusDot(data.database.status === 'ok' ? 'ok' : 'error') + ' ' + data.database.status);
                html += diagItem('Messages', data.database.message_count);
                html += diagItem('Threads', data.database.thread_count);
                html += diagItem('File Size', formatBytes(data.database.file_size_bytes));
                html += '</div>';
            }

            if (data.providers) {
                html += '<div class="diag-section"><h4>AI Providers</h4>';
                Object.keys(data.providers).forEach(function(name) {
                    var p = data.providers[name];
                    var status = p.status === 'ok' ? 'ok' : (p.status === 'configured' ? 'warn' : 'error');
                    var detail = p.model_count ? p.model_count + ' models' : (p.error || p.status);
                    html += diagItem(name, statusDot(status) + ' ' + detail);
                });
                html += '</div>';
            }

            if (data.settings) {
                html += '<div class="diag-section"><h4>Current Settings</h4>';
                html += diagItem('Model', data.settings.global_model);
                html += diagItem('Provider', data.settings.global_provider);
                html += diagItem('History Limit', data.settings.max_channel_history);
                html += diagItem('Time Window', data.settings.time_window_hours + 'h');
                html += diagItem('Prune Every', data.settings.prune_frequency_hours + 'h');
                html += diagItem('Intent Detection', data.settings.intent_enabled ? 'Enabled' : 'Disabled');
                html += '</div>';
            }

            container.innerHTML = html;
        } catch (e) {
            container.innerHTML = '<div class="empty-state">Error: ' + escapeHtml(e.message) + '</div>';
        }
    }

    async function runPrune() {
        if (!confirm('Run data pruning now? This will remove old messages, threads, and reminders.')) return;
        try {
            const data = await api('POST', '/api/diagnostics/prune');
            var s = data.stats;
            alert('Pruning complete:\n' +
                'Messages: ' + s.messages_pruned + '\n' +
                'Threads: ' + s.threads_pruned + '\n' +
                'Reminders: ' + s.reminders_pruned + '\n' +
                'Trivia sessions: ' + s.trivia_sessions_pruned);
        } catch (e) {
            alert('Prune error: ' + e.message);
        }
    }

    function diagItem(label, value) {
        return '<div class="diag-item"><span class="label">' + escapeHtml(label) + '</span><span class="diag-status">' + value + '</span></div>';
    }

    function statusDot(type) {
        return '<span class="dot ' + type + '"></span>';
    }

    // ── Image Generation ─────────────────────────────────────

    var imageModelsCache = null;

    async function loadImageSettings() {
        try {
            var data = await api('GET', '/api/image/settings');

            // Set active provider
            $('#image-active-provider').value = data.active_provider || 'ai_horde';

            // Show available providers
            var badgesHtml = '';
            var allProviders = ['ai_horde', 'cloudflare', 'openai', 'comfyui', 'openrouter'];
            var available = data.available_providers || [];
            allProviders.forEach(function(p) {
                var isAvail = available.indexOf(p) !== -1;
                badgesHtml += '<span class="provider-badge ' + (isAvail ? 'available' : 'unavailable') + '">' + escapeHtml(p) + '</span>';
            });
            $('#image-available-providers').innerHTML = badgesHtml;

            // Load provider configs
            var configs = data.configs || {};
            loadProviderConfigValues(configs);

            // Load modalities
            var modalities = data.openrouter_modalities || ['image', 'text'];
            $('#mod-image').checked = modalities.indexOf('image') !== -1;
            $('#mod-text').checked = modalities.indexOf('text') !== -1;
            $('#mod-audio').checked = modalities.indexOf('audio') !== -1;
            updateModalitiesPreview();

            // Show correct config panel
            showProviderConfigPanel($('#image-config-provider').value);

            // Load OpenRouter image models
            loadOpenRouterImageModels(configs.openrouter ? configs.openrouter.model : null);
        } catch (e) {
            console.error('Failed to load image settings:', e);
        }
    }

    function loadProviderConfigValues(configs) {
        // AI Horde
        var horde = configs.ai_horde || {};
        $('#horde-model').value = horde.model || 'stable_diffusion_xl';
        $('#horde-size').value = horde.size || '1024x1024';
        $('#horde-steps').value = horde.steps || 30;

        // Cloudflare
        var cf = configs.cloudflare || {};
        $('#cf-size').value = cf.size || '768x768';
        $('#cf-steps').value = cf.steps || 25;

        // OpenAI
        var oai = configs.openai || {};
        $('#oai-model').value = oai.model || 'dall-e-3';
        $('#oai-quality').value = oai.quality || 'standard';
        $('#oai-style').value = oai.style || 'vivid';

        // ComfyUI
        var comfy = configs.comfyui || {};
        $('#comfy-model').value = comfy.model || '';
        $('#comfy-size').value = comfy.size || '512x512';
        $('#comfy-steps').value = comfy.steps || 20;

        // OpenRouter
        var or = configs.openrouter || {};
        $('#or-aspect').value = or.aspect_ratio || '1:1';
        $('#or-image-size').value = or.image_size || '1K';
    }

    function showProviderConfigPanel(provider) {
        var panels = ['ai_horde', 'cloudflare', 'openai', 'comfyui', 'openrouter'];
        panels.forEach(function(p) {
            var el = document.getElementById('config-' + p);
            if (el) el.style.display = (p === provider) ? 'block' : 'none';
        });
    }

    async function loadOpenRouterImageModels(currentModel) {
        var selectEl = $('#or-model');
        if (!selectEl) return;

        if (imageModelsCache) {
            populateImageModelSelect(selectEl, imageModelsCache, currentModel);
            return;
        }

        selectEl.innerHTML = '<option value="">Loading image models...</option>';
        try {
            var models = await api('GET', '/api/image/models');
            imageModelsCache = models;
            populateImageModelSelect(selectEl, models, currentModel);
        } catch (e) {
            selectEl.innerHTML = '<option value="">Failed to load models</option>';
        }
    }

    function populateImageModelSelect(selectEl, models, currentValue) {
        var html = '';
        models.forEach(function(m) {
            var id = m.id || m;
            var name = m.name || id;
            var selected = (id === currentValue) ? ' selected' : '';
            var label = (id === currentValue) ? '> ' + name + ' (current)' : name;
            html += '<option value="' + escapeHtml(id) + '"' + selected + '>' + escapeHtml(label) + '</option>';
        });
        if (!html) {
            html = '<option value="">No image models available</option>';
        }
        selectEl.innerHTML = html;
    }

    function updateModalitiesPreview() {
        var modalities = [];
        if ($('#mod-image').checked) modalities.push('image');
        if ($('#mod-text').checked) modalities.push('text');
        if ($('#mod-audio').checked) modalities.push('audio');
        var preview = $('#modalities-preview');
        if (preview) preview.textContent = JSON.stringify(modalities);
    }

    async function saveImageProvider(e) {
        e.preventDefault();
        try {
            await api('PUT', '/api/image/settings', {
                active_provider: $('#image-active-provider').value,
            });
            showSaveStatus('image-provider-save-status', 'Provider saved', false);
        } catch (e) {
            showSaveStatus('image-provider-save-status', 'Error: ' + e.message, true);
        }
    }

    async function saveModalities(e) {
        e.preventDefault();
        var modalities = [];
        if ($('#mod-image').checked) modalities.push('image');
        if ($('#mod-text').checked) modalities.push('text');
        if ($('#mod-audio').checked) modalities.push('audio');

        if (modalities.length === 0) {
            showSaveStatus('modalities-save-status', 'Select at least one modality', true);
            return;
        }

        try {
            await api('PUT', '/api/image/settings', {
                openrouter_modalities: modalities,
            });
            showSaveStatus('modalities-save-status', 'Modalities saved', false);
        } catch (e) {
            showSaveStatus('modalities-save-status', 'Error: ' + e.message, true);
        }
    }

    async function saveProviderConfig(provider) {
        var config = {};

        switch (provider) {
            case 'ai_horde':
                config = {
                    model: $('#horde-model').value,
                    size: $('#horde-size').value,
                    steps: parseInt($('#horde-steps').value),
                };
                break;
            case 'cloudflare':
                config = {
                    size: $('#cf-size').value,
                    steps: parseInt($('#cf-steps').value),
                };
                break;
            case 'openai':
                config = {
                    model: $('#oai-model').value,
                    quality: $('#oai-quality').value,
                    style: $('#oai-style').value,
                };
                break;
            case 'comfyui':
                config = {
                    size: $('#comfy-size').value,
                    steps: parseInt($('#comfy-steps').value),
                };
                if ($('#comfy-model').value) config.model = $('#comfy-model').value;
                break;
            case 'openrouter':
                config = {
                    model: $('#or-model').value,
                    aspect_ratio: $('#or-aspect').value,
                    image_size: $('#or-image-size').value,
                };
                break;
        }

        try {
            await api('PUT', '/api/image/settings', {
                provider: provider,
                config: config,
            });
            showSaveStatus('config-save-' + provider, 'Config saved', false);
        } catch (e) {
            showSaveStatus('config-save-' + provider, 'Error: ' + e.message, true);
        }
    }

    // ── WebSocket ────────────────────────────────────────────

    function connectWs() {
        if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
            return;
        }

        if (!authToken) {
            console.warn('No auth token available for WebSocket connection');
            updateWsStatus('No Token', 'badge-warning');
            return;
        }

        var proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
        ws = new WebSocket(proto + '//' + location.host + '/ws');

        ws.onopen = function () {
            ws.send(JSON.stringify({ token: authToken }));
        };

        ws.onmessage = function (event) {
            var data;
            try { data = JSON.parse(event.data); } catch (e) { return; }

            if (data.type === 'connected') {
                updateWsStatus('Connected', 'badge-success');
                return;
            }

            if (data.type === 'error') {
                updateWsStatus('Auth Failed', 'badge-danger');
                return;
            }

            if (data.type === 'pong') return;

            addActivityEntry(data);

            var activeTab = document.querySelector('.nav-item.active');
            if (!activeTab) return;
            var tab = activeTab.dataset.tab;

            if (data.type === 'settings_updated' || data.type === 'intent_settings_updated') {
                if (tab === 'settings') loadSettings();
                if (tab === 'overview') loadOverview();
            }
            if (data.type === 'channel_updated' || data.type === 'channel_reset') {
                if (tab === 'channels') loadChannels();
            }
            if (data.type === 'thread_updated' || data.type === 'thread_deleted') {
                if (tab === 'threads') loadThreads();
            }
            if (data.type === 'image_settings_updated') {
                if (tab === 'image-gen') loadImageSettings();
            }
        };

        ws.onclose = function () {
            updateWsStatus('Disconnected', 'badge-warning');
            scheduleWsReconnect();
        };

        ws.onerror = function () {
            updateWsStatus('Error', 'badge-danger');
        };
    }

    function disconnectWs() {
        if (wsReconnectTimer) {
            clearTimeout(wsReconnectTimer);
            wsReconnectTimer = null;
        }
        if (ws) {
            ws.close();
            ws = null;
        }
    }

    function scheduleWsReconnect() {
        if (wsReconnectTimer) return;
        wsReconnectTimer = setTimeout(function () {
            wsReconnectTimer = null;
            if ($('#dashboard').style.display !== 'none') {
                connectWs();
            }
        }, WS_RECONNECT_DELAY);
    }

    function updateWsStatus(text, className) {
        var el = $('#ws-status');
        if (el) {
            el.textContent = text;
            el.className = 'badge ' + className;
        }
    }

    function addActivityEntry(data) {
        var feed = $('#activity-feed');
        if (!feed) return;

        var placeholder = feed.querySelector('.loading-text');
        if (placeholder) placeholder.remove();

        var entry = document.createElement('div');
        entry.className = 'activity-entry';

        var now = new Date();
        var timeStr = formatTime(data.timestamp ? new Date(data.timestamp) : now);

        var detail = '';
        switch (data.type) {
            case 'message_activity':
                detail = (data.author || 'unknown') + ' in #' + (data.channel_name || 'unknown') + ' (' + (data.guild || '') + ')';
                break;
            case 'settings_updated':
                detail = 'Fields: ' + (data.fields || []).join(', ');
                break;
            case 'intent_settings_updated':
                detail = 'Intent fields: ' + (data.fields || []).join(', ');
                break;
            case 'channel_updated':
                detail = 'Channel ' + (data.channel_id || '') + ': ' + (data.fields || []).join(', ');
                break;
            case 'channel_reset':
                detail = 'Channel ' + (data.channel_id || '') + ' reset to defaults';
                break;
            case 'thread_updated':
                detail = 'Thread ' + (data.thread_id || '') + ': ' + (data.fields || []).join(', ');
                break;
            case 'thread_deleted':
                detail = 'Thread ' + (data.thread_id || '') + ' deleted';
                break;
            case 'prune_completed':
                detail = JSON.stringify(data.stats || {});
                break;
            default:
                detail = JSON.stringify(data);
        }

        entry.innerHTML = '<span class="time">' + escapeHtml(timeStr) + '</span>' +
            '<span class="event-type">' + escapeHtml(data.type) + '</span>' +
            '<span class="detail">' + escapeHtml(detail) + '</span>';

        feed.insertBefore(entry, feed.firstChild);

        while (feed.children.length > 200) {
            feed.removeChild(feed.lastChild);
        }
    }

    // ── Periodic Refresh ─────────────────────────────────────

    function startPeriodicRefresh() {
        setInterval(function () {
            var activeTab = document.querySelector('.nav-item.active');
            if (activeTab && activeTab.dataset.tab === 'overview') {
                loadOverview();
            }
        }, 30000);

        setInterval(function () {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({ type: 'ping' }));
            }
        }, 30000);
    }

    // ── Event Bindings ───────────────────────────────────────

    function init() {
        // Login form
        $('#login-form').addEventListener('submit', async function (e) {
            e.preventDefault();
            var errorEl = $('#login-error');
            errorEl.style.display = 'none';

            try {
                var data = await api('POST', '/api/auth/login', {
                    secret: $('#secret-input').value,
                });
                authToken = data.token;
                $('#secret-input').value = '';
                showDashboard();
            } catch (err) {
                errorEl.textContent = 'Invalid secret. Please try again.';
                errorEl.style.display = 'block';
            }
        });

        // Logout
        $('#logout-btn').addEventListener('click', handleLogout);

        // Tab navigation
        $$('.nav-item').forEach(function (item) {
            item.addEventListener('click', function () {
                switchTab(this.dataset.tab);
            });
        });

        // Settings forms
        $('#settings-form').addEventListener('submit', saveSettings);
        $('#intent-form').addEventListener('submit', saveIntentSettings);

        // Provider change reloads model list
        $('#setting-provider').addEventListener('change', onProviderChange);

        // Model search filters
        setupModelSearch('setting-model-search', 'setting-model');
        setupModelSearch('intent-model-search', 'intent-model');
        setupModelSearch('channel-model-search', 'channel-edit-model');
        setupModelSearch('thread-model-search', 'thread-edit-model');

        // Channel modal
        $('#channel-edit-form').addEventListener('submit', saveChannel);
        $('#channel-modal-close').addEventListener('click', function () {
            $('#channel-modal').style.display = 'none';
        });
        $('#channel-reset-btn').addEventListener('click', resetChannel);

        // Thread modal
        $('#thread-edit-form').addEventListener('submit', saveThread);
        $('#thread-modal-close').addEventListener('click', function () {
            $('#thread-modal').style.display = 'none';
        });
        $('#thread-delete-btn').addEventListener('click', deleteThread);

        // Messages
        $('#msg-source-type').addEventListener('change', onSourceTypeChange);
        $('#msg-filter-btn').addEventListener('click', function () {
            loadMessages(1);
        });
        $('#msg-prev').addEventListener('click', function () {
            if (msgCurrentPage > 1) loadMessages(msgCurrentPage - 1);
        });
        $('#msg-next').addEventListener('click', function () {
            if (msgCurrentPage < msgTotalPages) loadMessages(msgCurrentPage + 1);
        });

        // Image Generation
        $('#image-provider-form').addEventListener('submit', saveImageProvider);
        $('#modalities-form').addEventListener('submit', saveModalities);
        $('#image-config-provider').addEventListener('change', function() {
            showProviderConfigPanel(this.value);
        });

        // Modality checkbox preview
        ['mod-image', 'mod-text', 'mod-audio'].forEach(function(id) {
            var el = document.getElementById(id);
            if (el) el.addEventListener('change', updateModalitiesPreview);
        });

        // OpenRouter image model search filter
        setupModelSearch('or-model-search', 'or-model');

        // Provider config forms
        var providerForms = ['ai_horde', 'cloudflare', 'openai', 'comfyui', 'openrouter'];
        providerForms.forEach(function(p) {
            var form = document.getElementById('config-form-' + p);
            if (form) {
                form.addEventListener('submit', function(e) {
                    e.preventDefault();
                    saveProviderConfig(p);
                });
            }
        });

        // Diagnostics
        $('#run-diagnostics-btn').addEventListener('click', runDiagnostics);
        $('#run-prune-btn').addEventListener('click', runPrune);

        // Clear activity
        $('#clear-activity-btn').addEventListener('click', function () {
            $('#activity-feed').innerHTML = '<p class="loading-text">Waiting for events...</p>';
        });

        // Close modals on backdrop click
        $$('.modal').forEach(function (modal) {
            modal.addEventListener('click', function (e) {
                if (e.target === modal) {
                    modal.style.display = 'none';
                }
            });
        });

        // Start periodic refresh
        startPeriodicRefresh();

        // Check auth on load
        checkAuth();
    }

    // Boot
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();

// ============= CUSTOM MODAL DIALOGS =============
// Modal state
let modalResolve = null;

function showModal({ title, message, icon = 'info', showInput = false, inputValue = '', showCancel = true, confirmText = 'OK', cancelText = 'Batal', danger = false }) {
    return new Promise((resolve) => {
        modalResolve = resolve;
        
        const overlay = document.getElementById('modal-overlay');
        const titleEl = document.getElementById('modal-title');
        const messageEl = document.getElementById('modal-message');
        const iconEl = document.getElementById('modal-icon');
        const inputEl = document.getElementById('modal-input');
        const cancelBtn = document.getElementById('modal-cancel');
        const confirmBtn = document.getElementById('modal-confirm');
        
        // Set content
        titleEl.textContent = title;
        messageEl.textContent = message;
        
        // Set icon
        iconEl.className = 'modal-icon';
        if (danger) iconEl.classList.add('danger');
        else if (icon === 'warning') iconEl.classList.add('warning');
        
        const iconMap = {
            'info': '#icon-info',
            'warning': '#icon-alert-triangle',
            'danger': '#icon-alert-triangle',
            'question': '#icon-info',
            'input': '#icon-edit'
        };
        iconEl.querySelector('use').setAttribute('href', iconMap[icon] || '#icon-info');
        
        // Show/hide input
        inputEl.style.display = showInput ? 'block' : 'none';
        inputEl.value = inputValue;
        
        // Show/hide cancel button
        cancelBtn.style.display = showCancel ? 'inline-flex' : 'none';
        
        // Set button text and style
        confirmBtn.textContent = confirmText;
        confirmBtn.className = 'modal-btn ' + (danger ? 'modal-btn-danger' : 'modal-btn-primary');
        cancelBtn.textContent = cancelText;
        
        // Show modal
        overlay.classList.add('show');
        
        if (showInput) {
            setTimeout(() => inputEl.focus(), 100);
        }
    });
}

function closeModal(result) {
    const overlay = document.getElementById('modal-overlay');
    overlay.classList.remove('show');
    if (modalResolve) {
        modalResolve(result);
        modalResolve = null;
    }
}

// Modal button event listeners
document.addEventListener('DOMContentLoaded', () => {
    const confirmBtn = document.getElementById('modal-confirm');
    const cancelBtn = document.getElementById('modal-cancel');
    const inputEl = document.getElementById('modal-input');
    const overlay = document.getElementById('modal-overlay');
    
    if (confirmBtn) {
        confirmBtn.addEventListener('click', () => {
            const input = inputEl.style.display !== 'none' ? inputEl.value : true;
            closeModal(input);
        });
    }
    
    if (cancelBtn) {
        cancelBtn.addEventListener('click', () => closeModal(null));
    }
    
    // Close on overlay click
    if (overlay) {
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) closeModal(null);
        });
    }
    
    // Close on Escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && overlay.classList.contains('show')) {
            closeModal(null);
        }
        if (e.key === 'Enter' && overlay.classList.contains('show') && inputEl.style.display !== 'none') {
            closeModal(inputEl.value);
        }
    });
});

// Helper functions
function showAlert(title, message) {
    return showModal({ title, message, showCancel: false });
}

function showConfirm(title, message, danger = false) {
    return showModal({ title, message, icon: danger ? 'danger' : 'warning', danger, confirmText: 'Ya', cancelText: 'Batal' });
}

function showPrompt(title, message, defaultValue = '') {
    return showModal({ title, message, icon: 'input', showInput: true, inputValue: defaultValue, confirmText: 'OK' });
}

// ============= ORIGINAL CODE =============
const chatMessages = document.getElementById('chat-messages');
const chatInput = document.getElementById('chat-input');
const sendButton = document.getElementById('send-button');
const statusIndicator = document.getElementById('status-indicator');

// Check health on load
let currentModel = 'NetOps Sentinel'; // Default name
checkHealth();

// Event listeners
if (sendButton) sendButton.addEventListener('click', sendMessage);
if (chatInput) {
    chatInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendMessage();
    });
}

async function checkHealth() {
    try {
        const response = await fetch('/health');
        const data = await response.json();
        
        // Update Ollama status
        const ollamaStatus = document.getElementById('ollama-status');
        const ollamaIcon = document.getElementById('ollama-status-icon');
        
        if (data.ollama_connected) {
            ollamaStatus.textContent = data.model || 'Connected';
            if (ollamaIcon) {
                ollamaIcon.classList.remove('error');
                ollamaIcon.classList.add('healthy');
            }
        } else {
            ollamaStatus.textContent = 'Not connected';
            if (ollamaIcon) {
                ollamaIcon.classList.remove('healthy');
                ollamaIcon.classList.add('error');
            }
        }
        
        // Update monitoring status
        const monitorStatus = document.getElementById('monitoring-status');
        if (monitorStatus && data.monitoring) {
            monitorStatus.textContent = data.monitoring.active ? 'Active' : 'Inactive';
        }
        
    } catch (error) {
        console.error('Health check failed:', error);
        const ollamaStatus = document.getElementById('ollama-status');
        if (ollamaStatus) ollamaStatus.textContent = 'Error';
    }
}

// Tab switching (sidebar)
function switchTab(tabName) {
    // Remove active from all tabs and panels
    document.querySelectorAll('.monitor-tab').forEach(tab => tab.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach(panel => panel.classList.remove('active'));
    
    // Activate selected tab and panel
    if (event && event.target) {
        event.target.closest('.monitor-tab').classList.add('active');
    }
    const panel = document.getElementById(`tab-${tabName}`);
    if (panel) panel.classList.add('active');
}

// Main content tab switching
function switchMainTab(tabName) {
    // Remove active from all tabs and panels
    document.querySelectorAll('.content-tab').forEach(tab => tab.classList.remove('active'));
    document.querySelectorAll('.main-tab-panel').forEach(panel => panel.classList.remove('active'));
    
    // Activate selected tab and panel
    if (event && event.target) {
        event.target.closest('.content-tab').classList.add('active');
    }
    const panel = document.getElementById(`main-tab-${tabName}`);
    if (panel) panel.classList.add('active');
}

// Metrics update
async function updateMetrics() {
    try {
        const response = await fetch('/monitoring/metrics/detailed');
        const data = await response.json();
        
        if (data.success && data.metrics) {
            const m = data.metrics;
            
            // Update compact metrics (new layout)
            updateMiniGauge('cpu', m.cpu.percent);
            updateMiniGauge('memory', m.memory.percent);
            updateMiniGauge('disk', m.disk.percent);
            
            // Uptime
            const uptimeEl = document.getElementById('uptime-value2');
            if (uptimeEl) uptimeEl.textContent = `${m.uptime_hours}h`;
            
            // Network totals
            document.getElementById('upload-value').textContent = `${m.network.bytes_sent_mb} MB`;
            document.getElementById('download-value').textContent = `${m.network.bytes_recv_mb} MB`;
            
            // ===== ENHANCED METRICS =====
            
            // CPU Per-Core
            if (m.cpu.per_core && m.cpu.per_core.length > 0) {
                updateCPUCores(m.cpu.per_core);
            }
            
            // Memory Breakdown
            const memUsedEl = document.getElementById('memory-used-gb');
            const memAvailableEl = document.getElementById('memory-available-gb');
            const memCachedEl = document.getElementById('memory-cached-gb');
            const memTotalEl = document.getElementById('memory-total-gb');
            if (memUsedEl) memUsedEl.textContent = `${m.memory.used_gb} GB`;
            if (memAvailableEl) memAvailableEl.textContent = `${m.memory.available_gb} GB`;
            if (memCachedEl) memCachedEl.textContent = `${m.memory.cached_gb} GB`;
            if (memTotalEl) memTotalEl.textContent = `${m.memory.total_gb} GB`;
            
            // Disk I/O
            const diskReadEl = document.getElementById('disk-read-mb');
            const diskWriteEl = document.getElementById('disk-write-mb');
            if (diskReadEl) diskReadEl.textContent = `${m.disk.read_mb} MB/s`;
            if (diskWriteEl) diskWriteEl.textContent = `${m.disk.write_mb} MB/s`;
            
            // Temperature Sensors
            if (m.temperatures && Object.keys(m.temperatures).length > 0) {
                updateTemperatures(m.temperatures);
            }
            
            // Per-Interface Metrics (update interface list with enhanced data)
            if (m.interfaces && m.interfaces.length > 0) {
                updateInterfacesEnhanced(m.interfaces);
            }
        }
    } catch (e) {
        console.error('Metrics update failed:', e);
    }
}

function updateCPUCores(coresData) {
    const container = document.getElementById('cpu-cores-grid');
    if (!container) return;
    
    container.innerHTML = coresData.map((pct, idx) => {
        let colorClass = 'low';
        if (pct >= 90) colorClass = 'high';
        else if (pct >= 70) colorClass = 'medium';
        
        return `
            <div class="cpu-core-item">
                <div class="core-label">Core ${idx}</div>
                <div class="core-bar">
                    <div class="core-bar-fill ${colorClass}" style="width: ${pct}%"></div>
                </div>
                <div class="core-value">${pct.toFixed(1)}%</div>
            </div>
        `;
    }).join('');
}

function updateTemperatures(temps) {
    const section = document.getElementById('temperature-section');
    const container = document.getElementById('temperature-grid');
    if (!section || !container) return;
    
    // Show section
    section.style.display = 'block';
    
    container.innerHTML = Object.entries(temps).map(([sensor, temp]) => {
        let tempClass = 'normal';
        if (temp >= 80) tempClass = 'hot';
        else if (temp >= 60) tempClass = 'warm';
        
        return `
            <div class="temp-item ${tempClass}">
                <span class="temp-label">${sensor}</span>
                <span class="temp-value">${temp}°C</span>
            </div>
        `;
    }).join('');
}

function updateInterfacesEnhanced(interfaces) {
    const list = document.getElementById('interface-list');
    if (!list) return;
    
    // Skip update if we're showing detailed view
    if (list.classList.contains('detailed-view')) {
        return;
    }
    
    // Filter ALL interfaces that are UP (not just those with traffic)
    const active = interfaces.filter(iface => iface.is_up).slice(0, 8);
    
    if (active.length > 0) {
        list.innerHTML = active.map(iface => {
            const errorRate = iface.errin + iface.errout;
            const hasErrors = errorRate > 0;
            
            return `
                <div class="interface-item enhanced">
                    <div class="iface-name" title="${iface.name}">${iface.name}</div>
                    <div class="iface-stats">
                        <span class="stat-item">
                            <span class="stat-icon">↑</span> ${iface.bytes_sent_mb} MB
                        </span>
                        <span class="stat-item">
                            <span class="stat-icon">↓</span> ${iface.bytes_recv_mb} MB
                        </span>
                        ${hasErrors ? `<span class="stat-item error-stat" title="Errors: ${errorRate}">⚠ ${errorRate}</span>` : ''}
                    </div>
                    <span class="status">
                        <span class="status-dot ${iface.is_up ? 'up' : 'down'}"></span>
                        ${iface.speed > 0 ? iface.speed + ' Mbps' : 'Up'}
                    </span>
                </div>
            `;
        }).join('');
    } else {
        list.innerHTML = '<div class="interface-item"><span class="name">No active interfaces</span></div>';
    }
}

function updateMiniGauge(name, percent) {
    const valueEl = document.getElementById(`${name}-value2`);
    const barEl = document.getElementById(`${name}-bar2`);
    
    if (valueEl) valueEl.textContent = `${percent.toFixed(1)}%`;
    
    if (barEl) {
        barEl.style.width = `${percent}%`;
        barEl.className = 'metric-bar-fill';
        if (percent >= 90) {
            barEl.classList.add('high');
        } else if (percent >= 70) {
            barEl.classList.add('medium');
        } else {
            barEl.classList.add('low');
        }
    }
}

// ============= WEBSOCKET REAL-TIME UPDATES =============

/**
 * WebSocket client for real-time metrics streaming
 * Replaces HTTP polling with persistent WebSocket connection
 */
class MetricsWebSocket {
    constructor() {
        this.ws = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 10;
        this.baseReconnectDelay = 1000; // 1 second
        this.maxReconnectDelay = 30000; // 30 seconds
        this.isConnecting = false;
        this.messageHandlers = [];
        this.statusHandlers = [];
    }
    
    getWebSocketUrl() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        return `${protocol}//${window.location.host}/ws/metrics`;
    }
    
    connect() {
        if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
            return;
        }
        
        if (this.isConnecting) return;
        this.isConnecting = true;
        
        try {
            this.ws = new WebSocket(this.getWebSocketUrl());
            
            this.ws.onopen = () => {
                console.log('📡 WebSocket connected');
                this.isConnecting = false;
                this.reconnectAttempts = 0;
                this.notifyStatus('connected');
            };
            
            this.ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    
                    // Handle ping/pong for keepalive
                    if (data.type === 'ping') {
                        this.ws.send(JSON.stringify({ type: 'pong' }));
                        return;
                    }
                    
                    // Handle metrics updates
                    if (data.type === 'metrics') {
                        this.handleMetricsUpdate(data.data);
                    }
                    
                    // Notify all message handlers
                    this.messageHandlers.forEach(handler => handler(data));
                    
                } catch (e) {
                    console.error('WebSocket message parse error:', e);
                }
            };
            
            this.ws.onclose = (event) => {
                console.log('📡 WebSocket disconnected', event.code);
                this.isConnecting = false;
                this.notifyStatus('disconnected');
                this.scheduleReconnect();
            };
            
            this.ws.onerror = (error) => {
                console.error('WebSocket error:', error);
                this.isConnecting = false;
                this.notifyStatus('error');
            };
            
        } catch (e) {
            console.error('WebSocket connection failed:', e);
            this.isConnecting = false;
            this.scheduleReconnect();
        }
    }
    
    scheduleReconnect() {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.log('Max reconnect attempts reached, stopping');
            this.notifyStatus('failed');
            return;
        }
        
        // Exponential backoff: 1s, 2s, 4s, 8s, ... up to max
        const delay = Math.min(
            this.baseReconnectDelay * Math.pow(2, this.reconnectAttempts),
            this.maxReconnectDelay
        );
        
        this.reconnectAttempts++;
        console.log(`📡 Reconnecting in ${delay/1000}s (attempt ${this.reconnectAttempts})`);
        this.notifyStatus('reconnecting');
        
        setTimeout(() => this.connect(), delay);
    }
    
    handleMetricsUpdate(metrics) {
        if (!metrics) return;
        
        // Update compact metrics (gauges)
        if (metrics.cpu) updateMiniGauge('cpu', metrics.cpu.percent);
        if (metrics.memory) updateMiniGauge('memory', metrics.memory.percent);
        if (metrics.disk) updateMiniGauge('disk', metrics.disk.percent);
        
        // Uptime
        const uptimeEl = document.getElementById('uptime-value2');
        if (uptimeEl && metrics.uptime_hours) uptimeEl.textContent = `${metrics.uptime_hours}h`;
        
        // Network totals
        if (metrics.network) {
            const uploadEl = document.getElementById('upload-value');
            const downloadEl = document.getElementById('download-value');
            if (uploadEl) uploadEl.textContent = `${metrics.network.bytes_sent_mb} MB`;
            if (downloadEl) downloadEl.textContent = `${metrics.network.bytes_recv_mb} MB`;
        }
        
        // CPU Per-Core
        if (metrics.cpu && metrics.cpu.per_core && metrics.cpu.per_core.length > 0) {
            updateCPUCores(metrics.cpu.per_core);
        }
        
        // Memory Breakdown
        if (metrics.memory) {
            const memUsedEl = document.getElementById('memory-used-gb');
            const memAvailableEl = document.getElementById('memory-available-gb');
            const memCachedEl = document.getElementById('memory-cached-gb');
            const memTotalEl = document.getElementById('memory-total-gb');
            if (memUsedEl) memUsedEl.textContent = `${metrics.memory.used_gb} GB`;
            if (memAvailableEl) memAvailableEl.textContent = `${metrics.memory.available_gb} GB`;
            if (memCachedEl) memCachedEl.textContent = `${metrics.memory.cached_gb} GB`;
            if (memTotalEl) memTotalEl.textContent = `${metrics.memory.total_gb} GB`;
        }
        
        // Disk I/O
        if (metrics.disk) {
            const diskReadEl = document.getElementById('disk-read-mb');
            const diskWriteEl = document.getElementById('disk-write-mb');
            if (diskReadEl) diskReadEl.textContent = `${metrics.disk.read_mb} MB/s`;
            if (diskWriteEl) diskWriteEl.textContent = `${metrics.disk.write_mb} MB/s`;
        }
        
        // Temperature Sensors
        if (metrics.temperatures && Object.keys(metrics.temperatures).length > 0) {
            updateTemperatures(metrics.temperatures);
        }
        
        // Per-Interface Metrics
        if (metrics.interfaces && metrics.interfaces.length > 0) {
            updateInterfacesEnhanced(metrics.interfaces);
        }
        
        // Real-time Latency updates (from WebSocket)
        if (metrics.latency && metrics.latency.length > 0) {
            metrics.latency.forEach(item => {
                let id = '';
                if (item.host === '8.8.8.8') id = 'latency-8888';
                else if (item.host === '1.1.1.1') id = 'latency-1111';
                else if (item.host === 'google.com') id = 'latency-google';
                
                const el = document.getElementById(id);
                if (el) {
                    if (item.reachable) {
                        el.textContent = `${item.latency_ms}ms`;
                        el.className = 'value';
                        if (item.latency_ms < 50) el.classList.add('good');
                        else if (item.latency_ms < 150) el.classList.add('medium');
                        else el.classList.add('bad');
                    } else {
                        el.textContent = 'Offline';
                        el.className = 'value bad';
                    }
                }
            });
        }
        
        // Real-time Bandwidth updates (from WebSocket)
        if (metrics.bandwidth) {
            const bwUploadEl = document.getElementById('bw-upload');
            const bwDownloadEl = document.getElementById('bw-download');
            if (bwUploadEl) bwUploadEl.textContent = `${metrics.bandwidth.upload_rate_kbps} KB/s`;
            if (bwDownloadEl) bwDownloadEl.textContent = `${metrics.bandwidth.download_rate_kbps} KB/s`;
        }
    }
    
    onMessage(handler) {
        this.messageHandlers.push(handler);
    }
    
    onStatus(handler) {
        this.statusHandlers.push(handler);
    }
    
    notifyStatus(status) {
        this.statusHandlers.forEach(handler => handler(status));
        updateConnectionIndicator(status);
    }
    
    send(message) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(message));
        }
    }
    
    requestRefresh() {
        this.send({ type: 'refresh' });
    }
    
    disconnect() {
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
    }
}

// Update connection status indicator in UI
function updateConnectionIndicator(status) {
    const indicator = document.getElementById('ws-status-indicator');
    const text = document.getElementById('ws-status-text');
    
    if (indicator) {
        indicator.className = 'ws-status-dot ' + status;
    }
    if (text) {
        const statusMap = {
            'connected': 'Live',
            'disconnected': 'Offline',
            'reconnecting': 'Reconnecting...',
            'error': 'Error',
            'failed': 'Failed'
        };
        text.textContent = statusMap[status] || status;
    }
}

// Global WebSocket instance
let metricsWS = null;

// Initialize WebSocket connection on page load
function initWebSocket() {
    metricsWS = new MetricsWebSocket();
    metricsWS.connect();
    
    // Log status changes
    metricsWS.onStatus(status => {
        console.log('WebSocket status:', status);
        
        // When connected, do initial fetch just to populate UI immediately
        if (status === 'connected') {
            updateLatency();
            updateBandwidth();
        }
    });
    
    // Note: Periodic updates are now handled via WebSocket metrics broadcast
    // No need for setInterval here
    
    // Initial network data fetch
    updateLatency();
    updateBandwidth();
}

// Start WebSocket when DOM is ready
document.addEventListener('DOMContentLoaded', initWebSocket);

// Network monitoring functions
async function updateLatency() {
    try {
        const response = await fetch('/network/latency');
        const data = await response.json();
        
        if (data.success && data.latencies) {
            data.latencies.forEach(item => {
                let id = '';
                if (item.host === '8.8.8.8') id = 'latency-8888';
                else if (item.host === '1.1.1.1') id = 'latency-1111';
                else if (item.host === 'google.com') id = 'latency-google';
                
                const el = document.getElementById(id);
                if (el) {
                    if (item.reachable) {
                        el.textContent = `${item.latency_ms}ms`;
                        el.className = 'value';
                        if (item.latency_ms < 50) el.classList.add('good');
                        else if (item.latency_ms < 150) el.classList.add('medium');
                        else el.classList.add('bad');
                    } else {
                        el.textContent = 'Offline';
                        el.className = 'value bad';
                    }
                }
            });
        }
    } catch (e) {
        console.error('Latency update failed:', e);
    }
}

async function updateBandwidth() {
    try {
        const response = await fetch('/network/bandwidth');
        const data = await response.json();
        
        if (data.success) {
            document.getElementById('bw-upload').textContent = `${data.upload_rate_kbps} KB/s`;
            document.getElementById('bw-download').textContent = `${data.download_rate_kbps} KB/s`;
        }
    } catch (e) {
        console.error('Bandwidth update failed:', e);
    }
}

async function updateInterfaces() {
    try {
        const response = await fetch('/network/interfaces');
        const data = await response.json();
        
        if (data.success && data.interfaces) {
            const list = document.getElementById('interface-list');
            
            // Skip update if we're showing detailed view
            if (list && list.classList.contains('detailed-view')) {
                return;
            }
            
            // Filter only active or important interfaces
            const active = data.interfaces.filter(iface => 
                iface.is_up && iface.addresses.some(a => 
                    a.address && !a.address.startsWith('127.') && !a.address.startsWith('::')
                )
            ).slice(0, 5);
            
            if (active.length > 0) {
                list.innerHTML = active.map(iface => `
                    <div class="interface-item">
                        <span class="name" title="${iface.name}">${iface.name}</span>
                        <span class="status">
                            <span class="status-dot ${iface.is_up ? 'up' : 'down'}"></span>
                            ${iface.speed > 0 ? iface.speed + 'Mbps' : 'Up'}
                        </span>
                    </div>
                `).join('');
            } else {
                list.innerHTML = '<div class="interface-item"><span class="name">No active interfaces</span></div>';
            }
        }
    } catch (e) {
        console.error('Interfaces update failed:', e);
    }
}

// Enhanced interface cards with detailed metrics (for Network tab)
async function renderDetailedInterfaceCards() {
    try {
        const response = await fetch('/monitoring/metrics/detailed');
        const data = await response.json();
        
        if (!data.success ||  !data.metrics || !data.metrics.interfaces) {
            return;
        }
        
        const interfaces = data.metrics.interfaces;
        const container = document.getElementById('interface-list');
        
        if (!container) return;
        
        // Skip update if we're showing detailed view
        if (container.classList.contains('detailed-view')) {
            return;
        }
        
        // Add class to remove height restriction
        container.classList.add('detailed-view');
        
        // Filter: Show all UP interfaces (not just those with traffic)
        const activeInterfaces = interfaces.filter(iface => iface.is_up);
        
        if (activeInterfaces.length === 0) {
            container.classList.remove('detailed-view');
            return; // Keep basic list if no active interfaces
        }
        
        // Add class to remove height restriction
        container.classList.add('detailed-view');
        
        // Replace with detailed cards
        container.innerHTML = activeInterfaces.map(iface => {
            const errorRate = iface.errin + iface.errout;
            const dropRate = iface.dropin + iface.dropout;
            const hasIssues = errorRate > 0 || dropRate > 0;
            const speedText = iface.speed > 0 ? `${iface.speed} Mbps` : 'Unknown Speed';
            const statusBg = iface.is_up ? 'rgba(0,255,136,0.15)' : 'rgba(255,71,87,0.15)';
            const statusColor = iface.is_up ? 'var(--success)' : 'var(--danger)';
            
            return `
                <div class="interface-card-detailed">
                    <div class="iface-card-header">
                        <div class="iface-card-title">
                            <span class="icon" style="color: ${statusColor}; width: 24px; height: 24px;">
                                <svg><use href="#icon-wifi"/></svg>
                            </span>
                            <div>
                                <h4>${iface.name}</h4>
                                <span class="iface-speed">${speedText} • MTU ${iface.mtu}</span>
                            </div>
                        </div>
                        <div class="iface-status-badge" style="background: ${statusBg}; color: ${statusColor};">
                            <span class="status-dot ${iface.is_up ? 'up' : 'down'}"></span>
                            ${iface.is_up ? 'Online' : 'Offline'}
                        </div>
                    </div>
                    
                    <div class="iface-card-stats">
                        <div class="iface-stat-item">
                            <span class="stat-label">
                                <span class="stat-icon" style="color: var(--success);">↑</span> Sent
                            </span>
                            <div class="stat-values">
                                <span class="stat-main">${iface.bytes_sent_mb.toFixed(2)} MB</span>
                                <span class="stat-sub">${iface.packets_sent.toLocaleString()} packets</span>
                            </div>
                        </div>
                        
                        <div class="iface-stat-item">
                            <span class="stat-label">
                                <span class="stat-icon" style="color: var(--accent);">↓</span> Received
                            </span>
                            <div class="stat-values">
                                <span class="stat-main">${iface.bytes_recv_mb.toFixed(2)} MB</span>
                                <span class="stat-sub">${iface.packets_recv.toLocaleString()} packets</span>
                            </div>
                        </div>
                        
                        ${hasIssues ? `
                        <div class="iface-stat-item">
                            <span class="stat-label">
                                <span class="stat-icon" style="color: var(--warning);">⚠</span> Issues
                            </span>
                            <div class="stat-values">
                                <span class="stat-main" style="color: var(--warning);">${errorRate + dropRate} total</span>
                                <span class="stat-sub">${errorRate} errors, ${dropRate} drops</span>
                            </div>
                        </div>
                        ` : `
                        <div class="iface-stat-item">
                            <span class="stat-label">
                                <span class="stat-icon" style="color: var(--success);">✓</span> Status
                            </span>
                            <div class="stat-values">
                                <span class="stat-main" style="color: var(--success);">Healthy</span>
                                <span class="stat-sub">No errors detected</span>
                            </div>
                        </div>
                        `}
                    </div>
                </div>
            `;
        }).join('');
        
    } catch (e) {
        console.error('Failed to render detailed interface cards:', e);
    }
}

// Refresh interfaces (called by refresh button)
function refreshInterfaces() {
    // Request fresh data via WebSocket
    if (metricsWS) {
        metricsWS.requestRefresh();
    }
}

// Note: Network monitoring updates now come via WebSocket
// Legacy polling code removed - all updates are real-time via /ws/metrics

// Chat utility functions
async function clearChat() {
    if (!await showConfirm('Bersihkan Chat?', 'Apakah Anda yakin ingin menghapus history chat sesi ini?', true)) return;
    
    const messages = document.getElementById('chat-messages');
    const oldThreadId = currentThreadId;
    
    // Clear from localStorage
    localStorage.removeItem('chatHistory_' + oldThreadId);
    
    // Clear from server async (non-blocking)
    fetch(`/agent/conversations/${oldThreadId}`, { method: 'DELETE' }).catch(() => {});
    
    // Generate new thread ID for new conversation
    currentThreadId = 'session-' + Date.now();
    localStorage.setItem('chatThreadId', currentThreadId);
    messages.innerHTML = `
        <div class="message agent">
            <div class="message-avatar">
                <span class="icon"><svg><use href="#icon-robot"/></svg></span>
            </div>
            <div class="message-content">
                <p>Chat dibersihkan. Sesi baru dimulai. Ada yang bisa saya bantu?</p>
            </div>
        </div>
    `;
}

// New Chat - Start completely fresh conversation
async function newChat() {
    if (await showConfirm('Mulai Percakapan Baru?', 'Riwayat sebelumnya akan tetap tersimpan di history.')) {
        const messages = document.getElementById('chat-messages');
        // Generate new thread ID (keep old history in localStorage)
        currentThreadId = 'session-' + Date.now();
        localStorage.setItem('chatThreadId', currentThreadId);
        messages.innerHTML = `
            <div class="message agent">
                <div class="message-avatar">
                    <span class="icon"><svg><use href="#icon-robot"/></svg></span>
                </div>
                <div class="message-content">
                    <p>Percakapan baru dimulai. Bagaimana saya bisa membantu Anda hari ini?</p>
                </div>
            </div>
        `;
        // Clear sidebar
        const list = document.getElementById('decision-list');
        if (list) list.innerHTML = `<div class="decision-item"><span>No messages yet</span></div>`;
    }
}

// Toggle history dropdown
function toggleHistoryDropdown() {
    const dropdown = document.getElementById('history-dropdown');
    const isVisible = dropdown.classList.contains('show');
    
    if (isVisible) {
        dropdown.classList.remove('show');
    } else {
        dropdown.classList.add('show');
        loadChatThreads(); // Refresh when opened
    }
}

// Close dropdown when clicking outside
document.addEventListener('click', function(e) {
    const dropdown = document.getElementById('history-dropdown');
    const btn = document.getElementById('btn-history');
    if (dropdown && !dropdown.contains(e.target) && !btn.contains(e.target)) {
        dropdown.classList.remove('show');
    }
});

// Toggle chat expand/collapse
let chatExpanded = false;
function toggleChatExpand() {
    const mainContainer = document.querySelector('.main-container');
    const monitoringSection = document.querySelector('.monitoring-section');
    const chatSidebar = document.querySelector('.chat-sidebar');
    const btn = document.getElementById('btn-expand-chat');
    const icon = btn.querySelector('use');
    
    chatExpanded = !chatExpanded;
    
    if (chatExpanded) {
        // Expand chat - hide monitoring section
        monitoringSection.style.display = 'none';
        mainContainer.style.gridTemplateColumns = '1fr';
        chatSidebar.style.maxWidth = '100%';
        chatSidebar.classList.add('expanded');
        icon.setAttribute('href', '#icon-minimize');
        btn.title = 'Minimize Chat';
    } else {
        // Collapse chat - show monitoring section
        monitoringSection.style.display = '';
        mainContainer.style.gridTemplateColumns = '1fr 360px';
        chatSidebar.style.maxWidth = '';
        chatSidebar.classList.remove('expanded');
        icon.setAttribute('href', '#icon-maximize');
        btn.title = 'Expand Chat';
    }
}

function exportChat() {
    const messages = document.querySelectorAll('.message');
    let text = '=== Chat Export ===\n\n';
    messages.forEach(msg => {
        const type = msg.classList.contains('user') ? 'USER' : 'AGENT';
        const content = msg.querySelector('.message-content').textContent.trim();
        text += `[${type}]\n${content}\n\n`;
    });
    
    const blob = new Blob([text], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `chat_export_${new Date().toISOString().slice(0,10)}.txt`;
    a.click();
    URL.revokeObjectURL(url);
}

function sendQuickCmd(cmd) {
    document.getElementById('chat-input').value = cmd;
    sendMessage();
}

// Session/thread ID for conversation memory - persist in localStorage
let currentThreadId = localStorage.getItem('chatThreadId');
if (!currentThreadId) {
    currentThreadId = 'session-' + Date.now();
    localStorage.setItem('chatThreadId', currentThreadId);
}

// LocalStorage chat history helpers
function saveChatHistory() {
    const messages = [];
    document.querySelectorAll('#chat-messages .message').forEach(msg => {
        const type = msg.classList.contains('user') ? 'user' : 'agent';
        const content = msg.querySelector('.message-content')?.textContent?.trim() || '';
        if (content) {
            messages.push({ role: type, content: content });
        }
    });
    
    // Save to localStorage (sync, immediate)
    localStorage.setItem('chatHistory_' + currentThreadId, JSON.stringify(messages));
    
    // Save to server (async, non-blocking)
    saveToServerAsync(messages);
}

async function saveToServerAsync(messages) {
    try {
        await fetch('/agent/history/bulk-save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                thread_id: currentThreadId,
                messages: messages
            })
        });
    } catch (e) {
        console.log('Server save failed, localStorage backup exists:', e);
    }
}

async function loadChatHistoryFromStorage() {
    // Try loading from server first (async)
    try {
        const response = await fetch(`/agent/history/${currentThreadId}`);
        const data = await response.json();
        
        if (data.success && data.messages && data.messages.length > 0) {
            const chatArea = document.getElementById('chat-messages');
            chatArea.innerHTML = '';
            data.messages.forEach(m => {
                addMessage(m.content, m.role);
            });
            updateHistorySidebar(data.messages);
            // Sync to localStorage
            localStorage.setItem('chatHistory_' + currentThreadId, JSON.stringify(data.messages));
            return true;
        }
    } catch (e) {
        console.log('Server load failed, trying localStorage:', e);
    }
    
    // Fallback to localStorage
    const saved = localStorage.getItem('chatHistory_' + currentThreadId);
    if (saved) {
        try {
            const messages = JSON.parse(saved);
            if (messages && messages.length > 0) {
                const chatArea = document.getElementById('chat-messages');
                chatArea.innerHTML = '';
                messages.forEach(m => {
                    addMessage(m.content, m.role);
                });
                updateHistorySidebar(messages);
                return true;
            }
        } catch (e) {
            console.error('Error loading chat history:', e);
        }
    }
    return false;
}

function updateHistorySidebar(messages) {
    // This function is now deprecated in favor of chat threads list
    // Keep for compatibility
}

// ============= CHAT THREADS MANAGEMENT =============

async function loadChatThreads() {
    const list = document.getElementById('chat-threads-list');
    if (!list) return;
    
    list.innerHTML = '<div class="thread-item loading">Loading...</div>';
    
    try {
        const response = await fetch('/agent/history/threads');
        const data = await response.json();
        
        if (!data.success || !data.threads || data.threads.length === 0) {
            list.innerHTML = '<div class="thread-item empty">No chat history yet</div>';
            return;
        }
        
        list.innerHTML = data.threads.map(t => {
            const isActive = t.thread_id === currentThreadId;
            const date = t.last_updated ? new Date(t.last_updated).toLocaleDateString('id-ID', {
                day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit'
            }) : '';
            return `
                <div class="thread-item ${isActive ? 'active' : ''}" onclick="switchToThread('${t.thread_id}')">
                    <div class="thread-info">
                        <span class="thread-preview">${t.preview || 'Empty chat'}</span>
                        <span class="thread-meta">${t.message_count} messages • ${date}</span>
                    </div>
                    <button class="thread-delete" onclick="event.stopPropagation(); deleteThread('${t.thread_id}')" title="Delete">
                        <span class="icon icon-sm"><svg><use href="#icon-trash"/></svg></span>
                    </button>
                </div>
            `;
        }).join('');
    } catch (e) {
        list.innerHTML = '<div class="thread-item error">Failed to load</div>';
        console.error('Failed to load threads:', e);
    }
}

async function switchToThread(threadId) {
    if (threadId === currentThreadId) return;
    
    // Save current chat first
    saveChatHistory();
    
    // Switch to new thread
    currentThreadId = threadId;
    localStorage.setItem('chatThreadId', threadId);
    
    // Load the selected thread's messages
    await loadChatHistoryFromStorage();
    
    // Refresh thread list to update active state
    loadChatThreads();
}

async function deleteThread(threadId) {
    if (!confirm('Hapus percakapan ini?')) return;
    
    try {
        // Delete from server
        await fetch(`/agent/conversations/${threadId}`, { method: 'DELETE' });
        // Delete from localStorage
        localStorage.removeItem('chatHistory_' + threadId);
        
        // If deleting current thread, start new chat
        if (threadId === currentThreadId) {
            currentThreadId = 'session-' + Date.now();
            localStorage.setItem('chatThreadId', currentThreadId);
            document.getElementById('chat-messages').innerHTML = `
                <div class="message agent">
                    <div class="message-avatar">
                        <span class="icon"><svg><use href="#icon-robot"/></svg></span>
                    </div>
                    <div class="message-content">
                        <p>Percakapan dihapus. Sesi baru dimulai.</p>
                    </div>
                </div>
            `;
        }
        
        // Refresh list
        loadChatThreads();
    } catch (e) {
        console.error('Failed to delete thread:', e);
    }
}

// Load chat threads on page load
document.addEventListener('DOMContentLoaded', () => {
    setTimeout(loadChatThreads, 500);
});

async function sendMessage() {
    const query = chatInput.value.trim();
    if (!query) return;

    // Add user message
    addMessage(query, 'user');
    chatInput.value = '';
    sendButton.disabled = true;

    // Add loading indicator
    const loadingId = addLoading();

    try {
        // Use LangGraph conversation endpoint with thread ID
        const response = await fetch('/agent/conversations/query', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                query: query, 
                thread_id: currentThreadId 
            })
        });

        const data = await response.json();
        removeLoading(loadingId);

        if (data.success) {
            addMessage(data.response, 'agent');
            
            // Check for high-risk confirmation pattern in agent response text
            const actionIdMatch = data.response.match(/Action ID\s*:\s*([\w-]+)/i);
            if (actionIdMatch && (
                data.response.includes('KONFIRMASI DIPERLUKAN') ||
                data.response.includes('PENDING_CONFIRMATION') ||
                data.response.includes('HIGH-RISK') ||
                data.response.includes('confirm_action')
            )) {
                const actionId = actionIdMatch[1].trim();
                handleHighRiskConfirmation(actionId, data.response);
            }
        } else {
            addMessage('Error: ' + data.response, 'agent');
        }
        
        // Save to localStorage after each exchange
        saveChatHistory();
    } catch (e) {
        removeLoading(loadingId);
        addMessage('Error: ' + e.message, 'agent');
    }

    sendButton.disabled = false;
}

/**
 * Handle high-risk action confirmation — inline in chat
 * Appends confirm/cancel buttons directly inside the chat message
 */
function handleHighRiskConfirmation(actionId, responseText) {
    // Extract action description from response (try multiple patterns)
    const aksiMatch = responseText.match(/Aksi\s*:\s*(.+)/i)
        || responseText.match(/Type\s*:\s*(.+)/i)
        || responseText.match(/Action\s*:\s*(.+)/i);
    const risikoMatch = responseText.match(/Risiko\s*:\s*(.+)/i)
        || responseText.match(/Risk\s*:\s*(.+)/i)
        || responseText.match(/Impact\s*:\s*(.+)/i);
    
    const aksi = aksiMatch ? aksiMatch[1].trim() : 'Aksi high-risk';
    const risiko = risikoMatch ? risikoMatch[1].trim() : 'Tinggi';
    
    // Create inline confirmation card
    const confirmDiv = document.createElement('div');
    confirmDiv.className = 'message agent';
    confirmDiv.innerHTML = `
        <div class="message-avatar">
            <span class="icon"><svg><use href="#icon-alert-triangle"/></svg></span>
        </div>
        <div class="message-content">
            <div class="confirm-card">
                <div class="confirm-header">
                    <span class="confirm-icon">⚠️</span>
                    <span class="confirm-title">Konfirmasi Diperlukan</span>
                </div>
                <div class="confirm-details">
                    <div class="confirm-row">
                        <span class="confirm-label">Aksi:</span>
                        <span class="confirm-value">${aksi}</span>
                    </div>
                    <div class="confirm-row">
                        <span class="confirm-label">Risiko:</span>
                        <span class="confirm-value risk-high">${risiko}</span>
                    </div>
                    <div class="confirm-row">
                        <span class="confirm-label">Action ID:</span>
                        <span class="confirm-value"><code>${actionId}</code></span>
                    </div>
                </div>
                <div class="confirm-actions" id="confirm-actions-${actionId}">
                    <button class="confirm-btn confirm-yes" onclick="confirmHighRiskAction('${actionId}')">
                        ✅ Ya, Lanjutkan
                    </button>
                    <button class="confirm-btn confirm-no" onclick="cancelHighRiskAction('${actionId}')">
                        ❌ Batalkan
                    </button>
                </div>
            </div>
        </div>
    `;
    chatMessages.appendChild(confirmDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

/**
 * User confirmed the high-risk action
 */
async function confirmHighRiskAction(actionId) {
    // Disable buttons immediately
    const actionsDiv = document.getElementById(`confirm-actions-${actionId}`);
    if (actionsDiv) {
        actionsDiv.innerHTML = '<span class="confirm-status pending">⏳ Mengeksekusi...</span>';
    }
    
    addMessage('Ya, lanjutkan.', 'user');
    const loadingId = addLoading();
    
    try {
        const response = await fetch('/agent/conversations/query', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                query: `[SYSTEM INSTRUCTION] User telah mengkonfirmasi aksi. Panggil tool confirm_action sekarang dengan parameter action_id="${actionId}". JANGAN panggil tool lain. JANGAN buat konfirmasi baru. HANYA panggil confirm_action(action_id="${actionId}").`, 
                thread_id: currentThreadId 
            })
        });
        
        const data = await response.json();
        removeLoading(loadingId);
        
        if (data.success) {
            addMessage(data.response, 'agent');
        } else {
            addMessage('Error: ' + data.response, 'agent');
        }
        
        // Update inline status
        if (actionsDiv) {
            actionsDiv.innerHTML = '<span class="confirm-status done">✅ Dikonfirmasi</span>';
        }
        saveChatHistory();
    } catch (e) {
        removeLoading(loadingId);
        addMessage('Error: ' + e.message, 'agent');
        if (actionsDiv) {
            actionsDiv.innerHTML = '<span class="confirm-status error">❌ Error</span>';
        }
    }
}

/**
 * User cancelled the high-risk action
 */
async function cancelHighRiskAction(actionId) {
    // Disable buttons immediately
    const actionsDiv = document.getElementById(`confirm-actions-${actionId}`);
    if (actionsDiv) {
        actionsDiv.innerHTML = '<span class="confirm-status pending">⏳ Membatalkan...</span>';
    }
    
    addMessage('Tidak, batalkan aksi tersebut.', 'user');
    const loadingId = addLoading();
    
    try {
        const response = await fetch('/agent/conversations/query', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                query: `[SYSTEM INSTRUCTION] User telah membatalkan aksi. Panggil tool cancel_action sekarang dengan parameter action_id="${actionId}". JANGAN panggil tool lain. HANYA panggil cancel_action(action_id="${actionId}").`, 
                thread_id: currentThreadId 
            })
        });
        
        const data = await response.json();
        removeLoading(loadingId);
        
        if (data.success) {
            addMessage(data.response, 'agent');
        } else {
            addMessage('Error: ' + data.response, 'agent');
        }
        
        // Update inline status
        if (actionsDiv) {
            actionsDiv.innerHTML = '<span class="confirm-status cancelled">🚫 Dibatalkan</span>';
        }
        saveChatHistory();
    } catch (e) {
        removeLoading(loadingId);
        addMessage('Error: ' + e.message, 'agent');
        if (actionsDiv) {
            actionsDiv.innerHTML = '<span class="confirm-status error">❌ Error</span>';
        }
    }
}

function addMessage(content, type) {
    const div = document.createElement('div');
    div.className = `message ${type}`;
    // Replaced emoji logic with SVG icons
    const iconFn = type === 'user' ? '#icon-user' : '#icon-robot';
    
    div.innerHTML = `
        <div class="message-avatar">
            <span class="icon"><svg><use href="${iconFn}"/></svg></span>
        </div>
        <div class="message-content">${formatMarkdown(content)}</div>
    `;
    chatMessages.appendChild(div);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// ============= COPY AS JSON =============
// When user selects chat content and presses Ctrl+C, copy as JSON format
chatMessages.addEventListener('copy', function(e) {
    const selection = window.getSelection();
    if (!selection || selection.isCollapsed) return;
    
    // Find all message elements that overlap with the selection
    const range = selection.getRangeAt(0);
    const allMessages = chatMessages.querySelectorAll('.message');
    const selectedMessages = [];
    
    allMessages.forEach(msg => {
        // Check if this message intersects with the selection
        if (range.intersectsNode(msg)) {
            const role = msg.classList.contains('user') ? 'user' : 'agent';
            const contentEl = msg.querySelector('.message-content');
            if (contentEl) {
                const content = contentEl.textContent.trim();
                if (content) {
                    selectedMessages.push({ role, content });
                }
            }
        }
    });
    
    if (selectedMessages.length > 0) {
        e.preventDefault();
        const json = JSON.stringify(selectedMessages, null, 2);
        e.clipboardData.setData('text/plain', json);
    }
});

function formatMarkdown(text) {
    // Basic markdown formatting
    return text
        .replace(/^### (.+)$/gm, '<h3>$1</h3>')
        .replace(/^## (.+)$/gm, '<h2>$1</h2>')
        .replace(/^# (.+)$/gm, '<h1>$1</h1>')
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/`([^`]+)`/g, '<code>$1</code>')
        .replace(/^- (.+)$/gm, '• $1<br>')
        .replace(/\n/g, '<br>');
}

function addLoading() {
    const id = 'loading-' + Date.now();
    const div = document.createElement('div');
    div.id = id;
    div.className = 'message agent';
    div.innerHTML = `
        <div class="loading">
            <div class="loading-spinner"></div>
            <span>Processing with ${currentModel}...</span>
        </div>
    `;
    chatMessages.appendChild(div);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    return id;
}

function removeLoading(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
}

async function runTool(tool) {
    let params = {};
    
    if (tool === 'ping' || tool === 'port_scan' || tool === 'dns') {
        const host = await showPrompt('Run ' + tool, 'Enter hostname or IP (e.g., google.com):');
        if (!host) return;
        params = tool === 'dns' ? { hostname: host } : { host: host };
    }

    addMessage(`Running ${tool}...`, 'user');
    const loadingId = addLoading();

    try {
        const response = await fetch('/tools/run', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tool, params })
        });

        const data = await response.json();
        removeLoading(loadingId);

        let output = data.output || data.error;
        
        // Format common raw errors
        if (output && output.includes('ERR_NGROK')) {
            output = `❌ **Connection Failed**\nEndpoint is offline or unreachable.\nCode: ${output.match(/ERR_NGROK_\d+/)?.[0] || 'Unknown'}`;
        } else if (output) {
            // Clean up any "Error:" prefixes aggressively (start of string or after newlines)
            output = output.replace(/^(Error:\s*)+/i, '').replace(/\n(Error:\s*)+/gi, '\n');
        }

        const status = data.success ? '✓' : '✗';
        const formatted = data.success ? 
            `\`\`\`\n${output}\n\`\`\`` : 
            `${output}`; // Don't code-block simple errors
            
        addMessage(`${status} ${tool} result:\n${formatted}`, 'agent');
    } catch (e) {
        removeLoading(loadingId);
        addMessage('Tool execution failed: ' + e.message, 'agent');
    }
}

async function loadConversationHistory() {
    // Use localStorage-based history instead of server API
    // This is more reliable since server-side MemorySaver doesn't persist properly
    loadChatHistoryFromStorage();
}

// ============= INFRASTRUCTURE MONITORING FUNCTIONS =============

let monitoringRunning = false;

async function toggleMonitoring() {
    const btn = document.getElementById('btn-monitor-toggle');
    const btnText = document.getElementById('monitor-btn-text');
    const icon = btn.querySelector('use');
    
    try {
        if (monitoringRunning) {
            // Stop monitoring
            const response = await fetch('/infra/monitor/stop', { method: 'POST' });
            const data = await response.json();
            if (data.success) {
                monitoringRunning = false;
                btnText.textContent = 'Start';
                icon.setAttribute('href', '#icon-play');
                btn.classList.remove('active');
            }
        } else {
            // Start monitoring
            const response = await fetch('/infra/monitor/start', { method: 'POST' });
            const data = await response.json();
            if (data.success) {
                monitoringRunning = true;
                btnText.textContent = 'Stop';
                icon.setAttribute('href', '#icon-stop');
                btn.classList.add('active');
            }
        }
    } catch (e) {
        console.error('Toggle monitoring failed:', e);
    }
}

async function checkAllDevices() {
    try {
        addMessage('Checking all devices...', 'user');
        const loadingId = addLoading();
        
        const response = await fetch('/infra/monitor/check-all', { method: 'POST' });
        const data = await response.json();
        
        removeLoading(loadingId);
        
        if (data.success) {
            const resultCount = Object.keys(data.results).length;
            addMessage(`✓ Checked ${resultCount} devices`, 'agent');
            updateDeviceList();
            updateInfraSummary();
        } else {
            addMessage('Failed to check devices', 'agent');
        }
    } catch (e) {
        console.error('Check all devices failed:', e);
    }
}

async function showAddDevice() {
    const name = await showPrompt('Add New Device', 'Device Name (e.g., Router Utama):');
    if (!name) return;
    
    const ip = await showPrompt('Add New Device', 'IP Address (e.g., 192.168.1.1):');
    if (!ip) return;
    
    const type = await showPrompt('Add New Device', 'Device Type (router/switch/server/pc/printer/access_point/firewall/other):', 'other');
    
    // Connection protocol
    const protocol = await showPrompt('Remote Access (optional)', 'Connection Protocol (ssh/telnet/none):', 'none');
    let sshUser = '', sshPass = '', sshPort = 22;
    
    if (protocol === 'ssh' || protocol === 'telnet') {
        sshUser = await showPrompt(`${protocol.toUpperCase()} Credentials`, 'Username:');
        if (sshUser) {
            sshPass = await showPrompt(`${protocol.toUpperCase()} Credentials`, 'Password:');
            const defaultPort = protocol === 'ssh' ? '22' : '23';
            const portStr = await showPrompt(`${protocol.toUpperCase()} Credentials`, 'Port:', defaultPort);
            sshPort = parseInt(portStr) || (protocol === 'ssh' ? 22 : 23);
        }
    }
    
    addDevice(name, ip, type || 'other', protocol || 'none', sshUser, sshPass, sshPort);
}

async function addDevice(name, ip, type, protocol = 'none', sshUsername = '', sshPassword = '', sshPort = 22) {
    try {
        const response = await fetch('/infra/devices', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: name,
                ip: ip,
                type: type,
                description: '',
                location: '',
                ports_to_monitor: [],
                check_interval: 60,
                connection_protocol: protocol,
                ssh_username: sshUsername,
                ssh_password: sshPassword,
                ssh_port: sshPort
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            const protoNote = protocol !== 'none' ? ` (${protocol.toUpperCase()} enabled)` : '';
            addMessage(`✓ Device "${name}" (${ip}) added${protoNote}`, 'agent');
            updateDeviceList();
            updateInfraSummary();
        } else {
            addMessage(`Failed to add device: ${data.error || 'Unknown error'}`, 'agent');
        }
    } catch (e) {
        console.error('Add device failed:', e);
        addMessage('Failed to add device: ' + e.message, 'agent');
    }
}

async function updateDeviceList() {
    try {
        const response = await fetch('/infra/devices');
        const data = await response.json();
        
        const container = document.getElementById('devices-grid');
        if (!container) return;
        
        if (data.count === 0) {
            container.innerHTML = `
                <div class="device-empty">
                    <span class="icon icon-xl"><svg><use href="#icon-plus"/></svg></span>
                    <p>No devices registered</p>
                    <button class="btn-add-device" onclick="showAddDevice()">Add First Device</button>
                </div>
            `;
            return;
        }
        
        container.innerHTML = `
            <div class="device-list">
                <div class="device-list-header">
                    <span class="col-status">Status</span>
                    <span class="col-name">Name</span>
                    <span class="col-ip">IP Address</span>
                    <span class="col-type">Type</span>
                    <span class="col-uptime">Uptime</span>
                    <span class="col-actions">Actions</span>
                </div>
                ${data.devices.map(device => {
                    const statusClass = device.status || 'unknown';
                    const lastCheck = device.last_check ? new Date(device.last_check).toLocaleTimeString() : '-';
                    
                    return `
                        <div class="device-row" data-device-id="${device.id}" onclick="onDeviceRowClick(event, '${device.id}', '${device.name}', '${device.ip}', '${device.status || 'unknown'}', ${device.remote_configured || false}, '${device.connection_protocol || 'none'}')">
                            <span class="col-status">
                                <span class="status-badge ${statusClass}">
                                    <span class="status-dot"></span>
                                    ${device.status || 'Unknown'}
                                </span>
                            </span>
                            <span class="col-name">${device.name}</span>
                            <span class="col-ip">${device.ip}</span>
                            <span class="col-type">${device.type}</span>
                            <span class="col-uptime">${(device.uptime_percent || 0).toFixed(1)}%</span>
                            <span class="col-actions">
                                <button class="row-action check" onclick="checkDevice('${device.id}')" title="Check">
                                    <span class="icon icon-sm"><svg><use href="#icon-activity"/></svg></span>
                                </button>
                                <button class="row-action edit" onclick="editDevice('${device.id}', '${device.name}', '${device.ip}', '${device.type}')" title="Edit">
                                    <span class="icon icon-sm"><svg><use href="#icon-wrench"/></svg></span>
                                </button>
                                <button class="row-action delete" onclick="deleteDevice('${device.id}', '${device.name}')" title="Delete">
                                    <span class="icon icon-sm"><svg><use href="#icon-trash"/></svg></span>
                                </button>
                            </span>
                        </div>
                    `;
                }).join('')}
            </div>
        `;
        
    } catch (e) {
        console.error('Update device list failed:', e);
    }
}

// Helper function for device icons
function getDeviceIcon(type) {
    const icons = {
        'router': '#icon-router',
        'switch': '#icon-switch',
        'server': '#icon-server',
        'pc': '#icon-pc',
        'printer': '#icon-printer',
        'access_point': '#icon-wifi',
        'firewall': '#icon-lock'
    };
    return icons[type] || '#icon-server';
}

// Check single device
async function checkDevice(deviceId) {
    try {
        addMessage(`Checking device...`, 'user');
        const response = await fetch(`/infra/devices/${deviceId}/status`);
        const data = await response.json();
        
        if (data.device) {
            addMessage(`✓ ${data.device.name}: ${data.device.status}`, 'agent');
        }
        updateDeviceList();
        updateInfraSummary();
    } catch (e) {
        console.error('Check device failed:', e);
    }
}

// Edit device
function editDevice(deviceId, currentName, currentIp, currentType) {
    const name = prompt('Device Name:', currentName);
    if (name === null) return; // Cancelled
    
    const ip = prompt('IP Address:', currentIp);
    if (ip === null) return; // Cancelled
    
    const type = prompt('Device Type (router/switch/server/pc/printer/access_point/firewall/other):', currentType);
    if (type === null) return; // Cancelled
    
    updateDevice(deviceId, name || currentName, ip || currentIp, type || currentType);
}

async function updateDevice(deviceId, name, ip, type) {
    try {
        const response = await fetch(`/infra/devices/${deviceId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: name,
                ip: ip,
                type: type,
                description: '',
                location: '',
                ports_to_monitor: [],
                check_interval: 60
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            addMessage(`✓ Device "${name}" updated`, 'agent');
            updateDeviceList();
        } else {
            addMessage(`Failed to update device`, 'agent');
        }
    } catch (e) {
        console.error('Update device failed:', e);
        addMessage('Failed to update device: ' + e.message, 'agent');
    }
}

// Delete device
async function deleteDevice(deviceId, deviceName) {
    if (!await showConfirm('Delete Device?', `Are you sure you want to delete "${deviceName}"?`, true)) {
        return;
    }
    
    try {
        const response = await fetch(`/infra/devices/${deviceId}`, {
            method: 'DELETE'
        });
        
        const data = await response.json();
        
        if (data.success) {
            addMessage(`✓ Device "${deviceName}" deleted`, 'agent');
            updateDeviceList();
            updateInfraSummary();
        } else {
            addMessage(`Failed to delete device`, 'agent');
        }
    } catch (e) {
        console.error('Delete device failed:', e);
        addMessage('Failed to delete device: ' + e.message, 'agent');
    }
}

async function updateInfraSummary() {
    try {
        const response = await fetch('/infra/summary');
        const data = await response.json();
        
        document.getElementById('infra-total').textContent = data.total || 0;
        document.getElementById('infra-online').textContent = data.online || 0;
        document.getElementById('infra-offline').textContent = data.offline || 0;
        
    } catch (e) {
        console.error('Update infra summary failed:', e);
    }
}

async function updateAlerts() {
    try {
        const response = await fetch('/infra/alerts?limit=10');
        const data = await response.json();
        
        const alertList = document.getElementById('alert-list');
        const alertCount = document.getElementById('alert-count');
        
        alertCount.textContent = data.count || 0;
        
        if (!data.alerts || data.alerts.length === 0) {
            alertList.innerHTML = '<div class="decision-item" style="opacity: 0.5;"><span>No alerts</span></div>';
            return;
        }
        
        alertList.innerHTML = data.alerts.slice(0, 5).map(alert => {
            const severityClass = alert.severity === 'critical' ? 'high' : 
                                 alert.severity === 'warning' ? 'medium' : 'low';
            return `
                <div class="decision-item">
                    <span class="risk-badge ${severityClass}">${alert.severity.toUpperCase()}</span>
                    <span>${alert.message.substring(0, 40)}${alert.message.length > 40 ? '...' : ''}</span>
                </div>
            `;
        }).join('');
        
    } catch (e) {
        console.error('Update alerts failed:', e);
    }
}

async function checkMonitoringStatus() {
    try {
        const response = await fetch('/infra/monitor/status');
        const data = await response.json();
        
        const btn = document.getElementById('btn-monitor-toggle');
        const btnText = document.getElementById('monitor-btn-text');
        const icon = btn.querySelector('use');
        
        monitoringRunning = data.running;
        
        if (data.running) {
            btnText.textContent = 'Stop';
            icon.setAttribute('href', '#icon-stop');
            btn.classList.add('active');
        } else {
            btnText.textContent = 'Start';
            icon.setAttribute('href', '#icon-play');
            btn.classList.remove('active');
        }
    } catch (e) {
        console.error('Check monitoring status failed:', e);
    }
}

// Initial infrastructure monitoring load
updateDeviceList();
updateInfraSummary();
updateAlerts();
checkMonitoringStatus();

// ============= MODEL SELECTOR =============

async function initModelSelector() {
    const selector = document.getElementById('model-select');
    if (!selector) return;
    
    // Load current model
    try {
        const response = await fetch('/agent/models/list');
        const data = await response.json();
        if (data.success && data.current) {
            selector.value = data.current;
        }
    } catch (e) {
        console.error('Failed to load current model:', e);
    }
    
    // Handle model change
    selector.addEventListener('change', async (e) => {
        const modelId = e.target.value;
        const previousValue = selector.value;
        
        try {
            const response = await fetch('/agent/model/switch', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({model_id: modelId})
            });
            
            const data = await response.json();
            if (data.success) {
                console.log(`Switched to ${data.model.name}`);
                currentModel = data.model.name;
                // Optional: Show notification to user
                // You can add a toast/notification here
            } else {
                throw new Error(data.error || 'Failed to switch model');
            }
        } catch (e) {
            console.error('Model switch failed:', e);
            // Revert selection on error
            selector.value = previousValue;
            alert('Failed to switch model: ' + e.message);
        }
    });
}

// Auto-refresh infrastructure monitoring
setInterval(updateDeviceList, 10000);      // Every 10s
setInterval(updateInfraSummary, 10000);    // Every 10s
setInterval(updateAlerts, 15000);          // Every 15s
setInterval(checkMonitoringStatus, 5000);  // Every 5s

// Auto-refresh status cards
checkHealth(); // Initial check
setInterval(checkHealth, 10000);           // Every 10s

// Initial load
loadConversationHistory();
initModelSelector();

// ============= LOG WATCH =============

let logWatchRunning = false;
let logWatchPollInterval = null;

async function toggleLogWatch() {
    const btn = document.getElementById('btn-logwatch-toggle');
    const btnText = document.getElementById('logwatch-btn-text');
    
    try {
        if (logWatchRunning) {
            const response = await fetch('/logs/watch/stop', { method: 'POST' });
            const data = await response.json();
            if (data.success) {
                logWatchRunning = false;
                btnText.textContent = 'Log Watch';
                btn.classList.remove('logwatch-active');
                // Stop investigation polling
                if (logWatchPollInterval) {
                    clearInterval(logWatchPollInterval);
                    logWatchPollInterval = null;
                }
            }
        } else {
            const response = await fetch('/logs/watch/start', { method: 'POST' });
            const data = await response.json();
            if (data.success) {
                logWatchRunning = true;
                btnText.textContent = 'Watching...';
                btn.classList.add('logwatch-active');
                // Start polling for investigations
                startInvestigationPolling();
            }
        }
    } catch (e) {
        console.error('Toggle log watch failed:', e);
    }
}

function startInvestigationPolling() {
    if (logWatchPollInterval) return;
    logWatchPollInterval = setInterval(pollInvestigations, 5000);
}

async function pollInvestigations() {
    try {
        const response = await fetch('/logs/watch/investigations?unseen_only=true');
        const data = await response.json();
        
        if (!data.investigations || data.investigations.length === 0) {
            // Hide badge
            const badge = document.getElementById('logwatch-badge');
            if (badge) badge.style.display = 'none';
            return;
        }
        
        // Show badge count
        const badge = document.getElementById('logwatch-badge');
        if (badge) {
            badge.textContent = data.investigations.length;
            badge.style.display = '';
        }
        
        // Auto-open the latest unseen investigation as a new chat
        const latest = data.investigations[data.investigations.length - 1];
        await openInvestigationChat(latest);
        
    } catch (e) {
        console.error('Poll investigations failed:', e);
    }
}

async function openInvestigationChat(investigation) {
    // Mark as seen
    try {
        await fetch(`/logs/watch/investigations/${investigation.id}/seen`, { method: 'POST' });
    } catch (e) {
        console.error('Mark seen failed:', e);
    }
    
    // Save current chat
    saveChatHistory();
    
    // Switch to investigation thread
    currentThreadId = investigation.thread_id;
    localStorage.setItem('chatThreadId', currentThreadId);
    
    // Build investigation chat UI
    const chatMessages = document.getElementById('chat-messages');
    const severityEmoji = investigation.severity === 'critical' ? '🚨' : '⚠️';
    const severityClass = investigation.severity === 'critical' ? 'risk-high' : '';
    
    chatMessages.innerHTML = `
        <div class="message agent">
            <div class="message-avatar">
                <span class="icon"><svg><use href="#icon-alert-triangle"/></svg></span>
            </div>
            <div class="message-content">
                <div class="confirm-card">
                    <div class="confirm-header">
                        <span class="confirm-icon">${severityEmoji}</span>
                        <span class="confirm-title">Anomali Terdeteksi — Auto-Investigasi</span>
                    </div>
                    <div class="confirm-details">
                        <div class="confirm-row">
                            <span class="confirm-label">Device:</span>
                            <span class="confirm-value">${investigation.device_name} (${investigation.device_ip})</span>
                        </div>
                        <div class="confirm-row">
                            <span class="confirm-label">Severity:</span>
                            <span class="confirm-value ${severityClass}">${investigation.severity.toUpperCase()}</span>
                        </div>
                        <div class="confirm-row">
                            <span class="confirm-label">Pattern:</span>
                            <span class="confirm-value">${investigation.description}</span>
                        </div>
                        <div class="confirm-row">
                            <span class="confirm-label">Log:</span>
                            <span class="confirm-value"><code>${investigation.log_line}</code></span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        <div class="message agent">
            <div class="message-avatar">
                <span class="icon"><svg><use href="#icon-robot"/></svg></span>
            </div>
            <div class="message-content">
                <p>${formatMarkdown(investigation.agent_response || 'Investigasi sedang berlangsung...')}</p>
            </div>
        </div>
    `;
    
    // Check if agent response contains high-risk confirmation
    if (investigation.agent_response) {
        const actionIdMatch = investigation.agent_response.match(/Action ID\s*:\s*([\w-]+)/i);
        if (actionIdMatch && (
            investigation.agent_response.includes('KONFIRMASI DIPERLUKAN') ||
            investigation.agent_response.includes('confirm_action')
        )) {
            const actionId = actionIdMatch[1].trim();
            handleHighRiskConfirmation(actionId, investigation.agent_response);
        }
    }
    
    chatMessages.scrollTop = chatMessages.scrollHeight;
    saveChatHistory();
    
    // Refresh thread list
    loadChatThreads();
    
    // Hide badge for now
    const badge = document.getElementById('logwatch-badge');
    if (badge) badge.style.display = 'none';
}

// Check log watch status on page load
async function checkLogWatchStatus() {
    try {
        const response = await fetch('/logs/watch/status');
        const data = await response.json();
        
        if (data.running) {
            logWatchRunning = true;
            const btn = document.getElementById('btn-logwatch-toggle');
            const btnText = document.getElementById('logwatch-btn-text');
            if (btn) btn.classList.add('logwatch-active');
            if (btnText) btnText.textContent = 'Watching...';
            startInvestigationPolling();
        }
    } catch (e) {
        // Ignore
    }
}

// Init on load
document.addEventListener('DOMContentLoaded', () => {
    setTimeout(checkLogWatchStatus, 1000);
});

// ============= TERMINAL PANEL =============

let terminalOpen = false;
let terminalMaximized = false;
let terminalTabs = {};       // { tabId: { deviceId, deviceName, deviceIp, status, refreshInterval } }
let activeTerminalTab = null;
let terminalCounter = 0;

// Device row click handler
function onDeviceRowClick(event, deviceId, deviceName, deviceIp, deviceStatus, remoteConfigured, connectionProtocol) {
    // Don't open terminal if clicking action buttons
    if (event.target.closest('.col-actions')) return;
    openDeviceTerminal(deviceId, deviceName, deviceIp, deviceStatus, remoteConfigured, connectionProtocol);
}

// Toggle terminal panel open/close
function toggleTerminalPanel() {
    const panel = document.getElementById('terminal-panel');
    const btn = document.getElementById('btn-terminal-toggle');
    terminalOpen = !terminalOpen;
    
    if (terminalOpen) {
        panel.classList.add('open');
        btn.classList.add('active');
    } else {
        panel.classList.remove('open');
        btn.classList.remove('active');
        terminalMaximized = false;
        panel.classList.remove('maximized');
    }
}

// Toggle maximize
function toggleTerminalMaximize() {
    const panel = document.getElementById('terminal-panel');
    terminalMaximized = !terminalMaximized;
    
    if (terminalMaximized) {
        panel.classList.add('maximized');
    } else {
        panel.classList.remove('maximized');
    }
}

// Open a terminal tab for a device
function openDeviceTerminal(deviceId, deviceName, deviceIp, deviceStatus, remoteConfigured, connectionProtocol) {
    // Check if tab already exists for this device
    const existingTabId = Object.keys(terminalTabs).find(id => terminalTabs[id].deviceId === deviceId);
    
    if (existingTabId) {
        switchTerminalTab(existingTabId);
        if (!terminalOpen) toggleTerminalPanel();
        return;
    }
    
    // Create new tab
    terminalCounter++;
    const tabId = `term-${terminalCounter}`;
    
    terminalTabs[tabId] = {
        deviceId, deviceName, deviceIp, status: deviceStatus || 'unknown',
        remoteConfigured: !!remoteConfigured,
        connectionProtocol: connectionProtocol || 'none',
        refreshInterval: null
    };
    
    // Show terminal panel if not open
    if (!terminalOpen) toggleTerminalPanel();
    
    // Hide welcome message
    const welcome = document.getElementById('terminal-welcome');
    if (welcome) welcome.style.display = 'none';
    
    // Create tab button
    const tabsContainer = document.getElementById('terminal-tabs');
    const tab = document.createElement('button');
    tab.className = 'terminal-tab active';
    tab.id = `tab-btn-${tabId}`;
    tab.innerHTML = `
        <span class="tab-dot ${deviceStatus || 'unknown'}"></span>
        <span class="tab-label">${deviceName}</span>
        <span class="tab-close" onclick="event.stopPropagation(); closeTerminalTab('${tabId}')">
            <svg width="10" height="10" viewBox="0 0 24 24" stroke="currentColor" stroke-width="3" fill="none">
                <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
        </span>
    `;
    tab.onclick = (e) => { if (!e.target.closest('.tab-close')) switchTerminalTab(tabId); };
    
    // Deactivate other tabs
    tabsContainer.querySelectorAll('.terminal-tab').forEach(t => t.classList.remove('active'));
    tabsContainer.appendChild(tab);
    
    // Create output pane
    const body = document.getElementById('terminal-body');
    body.querySelectorAll('.terminal-output').forEach(o => o.classList.remove('active'));
    
    const output = document.createElement('div');
    output.className = 'terminal-output active';
    output.id = `output-${tabId}`;
    body.appendChild(output);
    
    activeTerminalTab = tabId;
    
    // Initial log lines
    appendTerminalLine(tabId, `Connected to ${deviceName} (${deviceIp})`, 'system');
    const proto = connectionProtocol || 'none';
    if (remoteConfigured && proto !== 'none') {
        appendTerminalLine(tabId, `${proto.toUpperCase()} enabled — commands will be executed on this device remotely.`, 'success');
    } else {
        appendTerminalLine(tabId, `No remote access configured — commands run locally. Edit device to add SSH/Telnet credentials.`, 'warning');
    }
    appendTerminalLine(tabId, `Loading health check logs...`, 'info');
    
    // Fetch existing logs
    fetchDeviceLogs(tabId, deviceId);
    
    // Set up auto-refresh every 10s
    terminalTabs[tabId].refreshInterval = setInterval(() => {
        fetchDeviceLogs(tabId, deviceId, true);
    }, 10000);
}

// Switch active terminal tab
function switchTerminalTab(tabId) {
    if (!terminalTabs[tabId]) return;
    activeTerminalTab = tabId;
    
    // Update tab buttons
    document.querySelectorAll('.terminal-tab').forEach(t => t.classList.remove('active'));
    const tabBtn = document.getElementById(`tab-btn-${tabId}`);
    if (tabBtn) tabBtn.classList.add('active');
    
    // Update output panes
    document.querySelectorAll('.terminal-output').forEach(o => o.classList.remove('active'));
    const output = document.getElementById(`output-${tabId}`);
    if (output) output.classList.add('active');
}

// Close a terminal tab
function closeTerminalTab(tabId) {
    const tab = terminalTabs[tabId];
    if (!tab) return;
    
    // Clear refresh interval
    if (tab.refreshInterval) clearInterval(tab.refreshInterval);
    
    // Remove tab button and output
    const tabBtn = document.getElementById(`tab-btn-${tabId}`);
    if (tabBtn) tabBtn.remove();
    const output = document.getElementById(`output-${tabId}`);
    if (output) output.remove();
    
    delete terminalTabs[tabId];
    
    // Switch to another tab or show welcome
    const remaining = Object.keys(terminalTabs);
    if (remaining.length > 0) {
        switchTerminalTab(remaining[remaining.length - 1]);
    } else {
        activeTerminalTab = null;
        const welcome = document.getElementById('terminal-welcome');
        if (welcome) welcome.style.display = 'flex';
    }
}

// Clear active terminal output
function clearActiveTerminal() {
    if (!activeTerminalTab) return;
    const output = document.getElementById(`output-${activeTerminalTab}`);
    if (output) output.innerHTML = '';
    appendTerminalLine(activeTerminalTab, 'Terminal cleared.', 'system');
}

// Append a line to terminal output
function appendTerminalLine(tabId, text, type = 'info') {
    const output = document.getElementById(`output-${tabId}`);
    if (!output) return;
    
    const now = new Date();
    const timeStr = now.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
    
    const line = document.createElement('div');
    line.className = `terminal-line ${type}`;
    line.innerHTML = `<span class="time">${timeStr}</span><span class="text">${escapeHtml(text)}</span>`;
    output.appendChild(line);
    
    // Auto-scroll to bottom
    output.scrollTop = output.scrollHeight;
    
    // Limit lines to 500
    while (output.children.length > 500) {
        output.removeChild(output.firstChild);
    }
}

// Escape HTML for security
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Fetch device logs from backend
async function fetchDeviceLogs(tabId, deviceId, isRefresh = false) {
    try {
        const response = await fetch(`/infra/devices/${deviceId}/logs?limit=30`);
        if (!response.ok) return;
        const data = await response.json();
        
        if (!isRefresh) {
            // Initial load — show all logs
            const output = document.getElementById(`output-${tabId}`);
            if (!output) return;
            
            if (data.logs.length === 0) {
                appendTerminalLine(tabId, 'No health check history yet. Click Check to run first scan.', 'info');
                return;
            }
            
            appendTerminalLine(tabId, `--- Health Check History (${data.logs.length} entries) ---`, 'system');
            
            for (const log of data.logs) {
                const time = new Date(log.time);
                const timeStr = time.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
                
                const line = document.createElement('div');
                line.className = `terminal-line ${log.type}`;
                line.innerHTML = `<span class="time">${timeStr}</span><span class="text">${escapeHtml(log.text)}</span>`;
                output.appendChild(line);
            }
            
            output.scrollTop = output.scrollHeight;
        } else {
            // Refresh — update tab status dot
            const tab = terminalTabs[tabId];
            if (tab && data.device_status !== tab.status) {
                tab.status = data.device_status;
                const dot = document.querySelector(`#tab-btn-${tabId} .tab-dot`);
                if (dot) dot.className = `tab-dot ${data.device_status}`;
                appendTerminalLine(tabId, `Status changed → ${data.device_status.toUpperCase()}`, 
                    data.device_status === 'online' ? 'success' : data.device_status === 'offline' ? 'error' : 'warning');
            }
        }
    } catch (e) {
        if (!isRefresh) appendTerminalLine(tabId, `Error fetching logs: ${e.message}`, 'error');
    }
}

// ============= TERMINAL DRAG RESIZE =============

(function initTerminalResize() {
    const handle = document.getElementById('terminal-drag-handle');
    const panel = document.getElementById('terminal-panel');
    if (!handle || !panel) return;
    
    let isResizing = false;
    let startY = 0;
    let startHeight = 0;
    
    handle.addEventListener('mousedown', (e) => {
        // Only start resize if not clicking buttons
        if (e.target.closest('.terminal-tab, .terminal-action-btn, .terminal-header-left')) return;
        
        isResizing = true;
        startY = e.clientY;
        startHeight = panel.offsetHeight;
        panel.classList.add('resizing');
        document.body.style.cursor = 'ns-resize';
        document.body.style.userSelect = 'none';
        e.preventDefault();
    });
    
    document.addEventListener('mousemove', (e) => {
        if (!isResizing) return;
        const delta = startY - e.clientY;
        const newHeight = Math.max(120, Math.min(window.innerHeight * 0.7, startHeight + delta));
        panel.style.height = newHeight + 'px';
    });
    
    document.addEventListener('mouseup', () => {
        if (!isResizing) return;
        isResizing = false;
        panel.classList.remove('resizing');
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
    });
})();

// ============= TERMINAL COMMAND INPUT =============

let commandHistory = [];
let historyIndex = -1;

document.addEventListener('DOMContentLoaded', () => {
    const input = document.getElementById('terminal-cmd-input');
    if (!input) return;
    
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && input.value.trim()) {
            const cmd = input.value.trim();
            commandHistory.unshift(cmd);
            if (commandHistory.length > 50) commandHistory.pop();
            historyIndex = -1;
            
            executeTerminalCommand(cmd);
            input.value = '';
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            if (historyIndex < commandHistory.length - 1) {
                historyIndex++;
                input.value = commandHistory[historyIndex];
            }
        } else if (e.key === 'ArrowDown') {
            e.preventDefault();
            if (historyIndex > 0) {
                historyIndex--;
                input.value = commandHistory[historyIndex];
            } else {
                historyIndex = -1;
                input.value = '';
            }
        }
    });
});

// Ensure a tab exists for command output (use active tab or create "General" tab)
function ensureCommandTab() {
    if (activeTerminalTab) return activeTerminalTab;
    
    // Create "General" tab
    terminalCounter++;
    const tabId = `term-${terminalCounter}`;
    
    terminalTabs[tabId] = {
        deviceId: null, deviceName: 'General', deviceIp: '', status: 'unknown',
        refreshInterval: null
    };
    
    if (!terminalOpen) toggleTerminalPanel();
    
    const welcome = document.getElementById('terminal-welcome');
    if (welcome) welcome.style.display = 'none';
    
    const tabsContainer = document.getElementById('terminal-tabs');
    const tab = document.createElement('button');
    tab.className = 'terminal-tab active';
    tab.id = `tab-btn-${tabId}`;
    tab.innerHTML = `
        <span class="tab-dot unknown"></span>
        <span class="tab-label">General</span>
        <span class="tab-close" onclick="event.stopPropagation(); closeTerminalTab('${tabId}')">
            <svg width="10" height="10" viewBox="0 0 24 24" stroke="currentColor" stroke-width="3" fill="none">
                <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
        </span>
    `;
    tab.onclick = (e) => { if (!e.target.closest('.tab-close')) switchTerminalTab(tabId); };
    
    tabsContainer.querySelectorAll('.terminal-tab').forEach(t => t.classList.remove('active'));
    tabsContainer.appendChild(tab);
    
    const body = document.getElementById('terminal-body');
    body.querySelectorAll('.terminal-output').forEach(o => o.classList.remove('active'));
    
    const output = document.createElement('div');
    output.className = 'terminal-output active';
    output.id = `output-${tabId}`;
    body.appendChild(output);
    
    activeTerminalTab = tabId;
    appendTerminalLine(tabId, 'Terminal ready. Type "help" for available commands.', 'system');
    
    return tabId;
}

// Execute a command and render output
async function executeTerminalCommand(cmd) {
    const tabId = ensureCommandTab();
    const tab = terminalTabs[tabId];
    
    // Show the command being executed
    appendTerminalLine(tabId, `$ ${cmd}`, 'system');
    
    // Determine endpoint: remote (SSH/Telnet) for device tabs, local otherwise
    let endpoint = '/infra/terminal/exec';
    if (tab && tab.deviceId && tab.remoteConfigured && tab.connectionProtocol !== 'none') {
        endpoint = `/infra/devices/${tab.deviceId}/remote/exec`;
    }
    
    try {
        const response = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ command: cmd })
        });
        
        const data = await response.json();
        
        if (data.lines && data.lines.length > 0) {
            const output = document.getElementById(`output-${tabId}`);
            if (!output) return;
            
            for (const log of data.lines) {
                // Skip the "$ command" echo from backend since we already showed it
                if (log.text.startsWith('$ ')) continue;
                
                const now = new Date();
                const timeStr = now.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
                
                const line = document.createElement('div');
                line.className = `terminal-line ${log.type}`;
                line.innerHTML = `<span class="time">${timeStr}</span><span class="text">${escapeHtml(log.text)}</span>`;
                output.appendChild(line);
            }
            
            output.scrollTop = output.scrollHeight;
        }
    } catch (e) {
        appendTerminalLine(tabId, `Error: ${e.message}`, 'error');
    }
}

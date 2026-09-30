/**
 * SentinelAI — Client-Side Application Controller
 *
 * Manages Single-Page Application (SPA) state transitions, API requests,
 * JWT authentication, 3-sample behavioral enrollment, and real-time
 * continuous behavioral monitoring.
 */

// =====================================================================
// Global Application State
// =====================================================================

const ENROLLMENT_PHRASE = "sentinel ai verifies typing biometrics";
const MIN_WINDOW_KEYSTROKES = 25; // Minimum keystroke events required before sending a feature window

const AppState = {
    currentView: 'login',
    user: null,
    token: null,
    enrollment: {
        isEnrolled: false,
        samplesCollected: 0,
        requiredSamples: 3
    },
    engines: {
        enrollKeystroke: null,
        enrollTypingdna: null,
        continuousKeystroke: null,
        unlockKeystroke: null,
        unlockTypingdna: null
    },
    monitoring: {
        active: false,
        sessionId: null,
        evaluating: false,
        pauseUntil: 0,
        minKeystrokes: MIN_WINDOW_KEYSTROKES,
        history: [], // Recent observations: [{ timestamp, score, level }]
        lastVerification: null,
        currentRisk: 0.0,
        currentLevel: 'LOW',
        status: 'SECURE',
        reauthRequired: false
    }
};

if (typeof window !== 'undefined') {
    window.AppState = AppState;
}


// =====================================================================
// Notifications Toast Helper
// =====================================================================

function showNotification(message, type = 'info') {
    const container = document.getElementById('notification-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `notification ${type}`;
    toast.innerHTML = `
        <span>${escapeHtml(message)}</span>
        <button class="notification-close" onclick="this.parentElement.remove()">&times;</button>
    `;

    container.appendChild(toast);

    setTimeout(() => {
        if (toast.parentElement) {
            toast.remove();
        }
    }, 4500);
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.innerText = text;
    return div.innerHTML;
}


// =====================================================================
// API Communication Layer (JWT Attached)
// =====================================================================

async function apiRequest(endpoint, options = {}) {
    const token = localStorage.getItem('sentinelai_token');
    const headers = {
        'Content-Type': 'application/json',
        ...(options.headers || {})
    };

    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }

    try {
        const response = await fetch(endpoint, {
            ...options,
            headers
        });

        // 401 Unauthorized handling: purge token and return to login (except auth credential checks)
        const isAuthCredentialCheck = endpoint.includes('/auth/login') || endpoint.includes('/auth/reauthenticate');
        if (response.status === 401 && !isAuthCredentialCheck) {
            stopContinuousMonitoring();
            localStorage.removeItem('sentinelai_token');
            localStorage.removeItem('sentinelai_user');
            AppState.token = null;
            AppState.user = null;
            showView('login');
            showNotification('Your session has expired. Please log in again.', 'warning');
            throw new Error('Authentication required');
        }

        // 403 Forbidden handling: session authorization failure
        if (response.status === 403) {
            stopContinuousMonitoring();
            showNotification('Session authorization failure. Please log in again.', 'error');
            showView('login');
            throw new Error('Session forbidden');
        }

        const data = await response.json().catch(() => ({}));

        if (!response.ok) {
            let errorMsg = 'An unexpected error occurred.';
            if (data && data.detail) {
                if (typeof data.detail === 'string') {
                    errorMsg = data.detail;
                } else if (Array.isArray(data.detail) && data.detail.length > 0) {
                    errorMsg = data.detail[0].msg || JSON.stringify(data.detail[0]);
                }
            } else if (data && data.message) {
                errorMsg = data.message;
            }
            throw new Error(errorMsg);
        }

        return data;
    } catch (err) {
        if (err.name === 'TypeError' && err.message.includes('fetch')) {
            throw new Error('Unable to connect to SentinelAI server. Please check your network connection.');
        }
        throw err;
    }
}

async function apiGet(endpoint) {
    return apiRequest(endpoint, { method: 'GET' });
}

async function apiPost(endpoint, body) {
    return apiRequest(endpoint, {
        method: 'POST',
        body: JSON.stringify(body)
    });
}


// =====================================================================
// View Management
// =====================================================================

function showView(viewId) {
    const previousView = AppState.currentView;
    AppState.currentView = viewId;

    const views = document.querySelectorAll('.view-section');
    views.forEach(v => v.classList.remove('active'));

    const targetView = document.getElementById(`view-${viewId}`);
    if (targetView) {
        targetView.classList.add('active');
    }

    // Update navbar user badge visibility
    const navUser = document.getElementById('nav-user');
    if (navUser) {
        if (AppState.user && (viewId === 'dashboard' || viewId === 'enrollment' || viewId === 'locked')) {
            navUser.style.display = 'flex';
            const userLabel = document.getElementById('user-display-name');
            if (userLabel) {
                userLabel.textContent = AppState.user.name || AppState.user.email || 'User';
            }
        } else {
            navUser.style.display = 'none';
        }
    }

    // Continuous Monitoring Lifecycle Guard
    // Monitoring MUST ONLY run when on 'dashboard'. Stop if switched away.
    if (viewId !== 'dashboard' && AppState.monitoring.active) {
        stopContinuousMonitoring();
    }
}

function showLogin() {
    showView('login');
}

function showRegister() {
    showView('register');
}

function showEnrollment() {
    showView('enrollment');
    setupEnrollmentEngines();
}

function showDashboard() {
    showView('dashboard');
    updateDashboardShell();

    const reauthBanner = document.getElementById('dash-reauth-banner');
    if (reauthBanner) {
        reauthBanner.style.display = AppState.monitoring.reauthRequired ? 'flex' : 'none';
    }

    // Start continuous monitoring if authenticated and enrolled
    if (AppState.user && AppState.enrollment.isEnrolled && !AppState.monitoring.active) {
        startContinuousMonitoring();
    }
}

function showLocked(reason = null) {
    showView('locked');
    setupLockedView(reason);
}


// =====================================================================
// Authentication Handlers
// =====================================================================

async function loginUser(email, password) {
    try {
        const result = await apiPost('/auth/login', {
            email: email.trim(),
            password: password
        });

        localStorage.setItem('sentinelai_token', result.access_token);
        const userInfo = {
            id: result.user_id,
            name: result.name,
            email: result.email
        };
        localStorage.setItem('sentinelai_user', JSON.stringify(userInfo));

        AppState.token = result.access_token;
        AppState.user = userInfo;

        showNotification('Login successful. Verifying biometric baseline...', 'success');
        await checkEnrollmentAndRoute();
    } catch (err) {
        showNotification(err.message || 'Login failed. Please check your credentials.', 'error');
    }
}

async function registerUser(name, email, password) {
    try {
        await apiPost('/auth/register', {
            name: name.trim(),
            email: email.trim(),
            password: password
        });

        showNotification('Account registered successfully! Please log in.', 'success');
        showView('login');

        const loginEmail = document.getElementById('login-email');
        if (loginEmail) {
            loginEmail.value = email;
        }
    } catch (err) {
        showNotification(err.message || 'Registration failed. Email may already be in use.', 'error');
    }
}

function logoutUser() {
    stopContinuousMonitoring();

    if (AppState.engines.enrollKeystroke) {
        AppState.engines.enrollKeystroke.stop();
    }
    if (AppState.engines.enrollTypingdna) {
        AppState.engines.enrollTypingdna.stop();
    }

    localStorage.removeItem('sentinelai_token');
    localStorage.removeItem('sentinelai_user');
    AppState.token = null;
    AppState.user = null;
    AppState.monitoring.sessionId = null;
    AppState.monitoring.history = [];
    AppState.monitoring.reauthRequired = false;

    showNotification('Logged out successfully.', 'info');
    showView('login');
}


// =====================================================================
// Enrollment Flow
// =====================================================================

async function checkEnrollmentAndRoute() {
    try {
        const status = await apiGet('/enrollment/status');
        AppState.enrollment.isEnrolled = status.is_enrolled;
        AppState.enrollment.samplesCollected = status.samples_collected;
        AppState.enrollment.requiredSamples = status.required_samples || 3;

        if (status.is_enrolled) {
            showDashboard();
        } else {
            showEnrollment();
            updateEnrollmentUI();
        }
    } catch (err) {
        console.error('Error checking enrollment status:', err);
    }
}

function setupEnrollmentEngines() {
    const inputEl = document.getElementById('enroll-input');
    if (!inputEl) return;

    inputEl.value = '';

    if (!AppState.engines.enrollKeystroke && window.SentinelKeystrokeEngine) {
        AppState.engines.enrollKeystroke = new window.SentinelKeystrokeEngine({
            targetElement: inputEl
        });
    }

    if (!AppState.engines.enrollTypingdna && window.TypingDNAClient) {
        AppState.engines.enrollTypingdna = new window.TypingDNAClient({
            targetElement: inputEl
        });
    }

    if (AppState.engines.enrollKeystroke) {
        AppState.engines.enrollKeystroke.start(inputEl);
    }
    if (AppState.engines.enrollTypingdna) {
        AppState.engines.enrollTypingdna.start(inputEl);
    }

    inputEl.oninput = () => {
        const countSpan = document.getElementById('enroll-key-count');
        if (countSpan && AppState.engines.enrollKeystroke) {
            countSpan.textContent = AppState.engines.enrollKeystroke.getSampleCount();
        }
    };
}

function updateEnrollmentUI() {
    const collected = AppState.enrollment.samplesCollected;
    const required = AppState.enrollment.requiredSamples;

    for (let i = 1; i <= 3; i++) {
        const node = document.getElementById(`step-node-${i}`);
        if (!node) continue;

        node.classList.remove('active', 'completed');
        if (i <= collected) {
            node.classList.add('completed');
            node.innerHTML = '&#10003;';
        } else if (i === collected + 1) {
            node.classList.add('active');
            node.textContent = i;
        } else {
            node.textContent = i;
        }
    }

    const progressFill = document.getElementById('progress-fill');
    if (progressFill) {
        const percent = Math.min(100, Math.round((collected / required) * 100));
        progressFill.style.width = `${percent}%`;
    }

    const samplePrompt = document.getElementById('enroll-sample-label');
    if (samplePrompt) {
        samplePrompt.textContent = `Sample ${collected + 1} of ${required}`;
    }

    const inputEl = document.getElementById('enroll-input');
    if (inputEl) {
        inputEl.value = '';
        inputEl.focus();
    }

    const countSpan = document.getElementById('enroll-key-count');
    if (countSpan) {
        countSpan.textContent = '0';
    }

    if (AppState.engines.enrollKeystroke) {
        AppState.engines.enrollKeystroke.reset();
    }
    if (AppState.engines.enrollTypingdna) {
        AppState.engines.enrollTypingdna.reset();
    }
}

async function submitEnrollmentSample() {
    const inputEl = document.getElementById('enroll-input');
    if (!inputEl) return;

    const typedText = inputEl.value.trim().toLowerCase();
    if (typedText !== ENROLLMENT_PHRASE) {
        showNotification('Please type the exact verification phrase as shown above.', 'warning');
        return;
    }

    if (!AppState.engines.enrollKeystroke) {
        showNotification('Keystroke engine not initialized.', 'error');
        return;
    }

    const features = AppState.engines.enrollKeystroke.getFeatures();

    let typingPattern = "";
    if (AppState.engines.enrollTypingdna) {
        typingPattern = AppState.engines.enrollTypingdna.getTypingPattern({
            type: 2,
            text: ENROLLMENT_PHRASE,
            targetId: 'enroll-input'
        });
    }

    try {
        const result = await apiPost('/enrollment/submit', {
            features: features,
            typing_pattern: typingPattern
        });

        AppState.enrollment.samplesCollected = result.samples_collected;
        AppState.enrollment.isEnrolled = result.is_enrolled;

        if (result.is_enrolled) {
            showNotification('Biometric enrollment complete! Establishing continuous session...', 'success');
            setTimeout(() => {
                showDashboard();
            }, 800);
        } else {
            showNotification(`Sample ${result.samples_collected} recorded! Please type the next sample.`, 'success');
            updateEnrollmentUI();
        }
    } catch (err) {
        showNotification(err.message || 'Failed to submit enrollment sample.', 'error');
    }
}


// =====================================================================
// Real-Time Continuous Behavioral Monitoring Layer
// =====================================================================

/**
 * Start live continuous behavioral monitoring on the dashboard.
 * - Creates a backend verification session if one does not exist.
 * - Attaches window-level SentinelKeystrokeEngine for passive 9-feature collection.
 * - Evaluates behavioral features on sliding windows of MIN_WINDOW_KEYSTROKES (25 keystrokes).
 */
async function startContinuousMonitoring() {
    if (AppState.monitoring.active) {
        return; // Idempotent: avoid duplicate monitoring loops
    }

    if (AppState.currentView !== 'dashboard' || !AppState.user || !AppState.enrollment.isEnrolled) {
        return;
    }

    // 1. Establish backend session if none active
    if (!AppState.monitoring.sessionId) {
        try {
            const sessionRes = await apiPost('/verification/start', { device_id: null });
            AppState.monitoring.sessionId = sessionRes.session_id;
        } catch (err) {
            setMonitoringIndicator('ERROR', 'SESSION ERROR');
            showNotification('Could not start verification session: ' + err.message, 'error');
            return;
        }
    }

    // 2. Initialize or reuse the continuous keystroke engine (window-level)
    if (!AppState.engines.continuousKeystroke && window.SentinelKeystrokeEngine) {
        AppState.engines.continuousKeystroke = new window.SentinelKeystrokeEngine({
            targetElement: null, // Global window monitoring
            listenMouse: true
        });
    }

    if (AppState.engines.continuousKeystroke) {
        AppState.engines.continuousKeystroke.reset();
        AppState.engines.continuousKeystroke.start();
    }

    AppState.monitoring.active = true;
    AppState.monitoring.evaluating = false;

    if (AppState.monitoring.reauthRequired) {
        setMonitoringIndicator('PAUSED', 'RE-AUTH REQUIRED');
    } else {
        setMonitoringIndicator('ACTIVE', 'LIVE MONITORING');
    }
    updateBufferUI(0);
}

/**
 * Stop live continuous monitoring completely.
 * Removes listeners, clears active flags, and resets the engine.
 */
function stopContinuousMonitoring() {
    if (!AppState.monitoring.active && !AppState.engines.continuousKeystroke) {
        return;
    }

    AppState.monitoring.active = false;
    AppState.monitoring.evaluating = false;

    if (AppState.engines.continuousKeystroke) {
        AppState.engines.continuousKeystroke.stop();
        AppState.engines.continuousKeystroke.reset();
    }

    setMonitoringIndicator('PAUSED', 'MONITORING PAUSED');
    updateBufferUI(0);
}

/**
 * Submit the current feature window to the backend.
 * Uses exact schema: POST /verification/features with { session_id, features }.
 * TypingDNA is NEVER called here (continuous monitoring relies on local personalized ML).
 */
async function submitFeatureWindow(force = false) {
    if (!AppState.monitoring.active || AppState.monitoring.evaluating) {
        return;
    }
    if (!AppState.monitoring.sessionId) {
        return;
    }
    if (Date.now() < AppState.monitoring.pauseUntil) {
        return; // Network backoff period active
    }
    if (!AppState.engines.continuousKeystroke) {
        return;
    }

    const sampleCount = AppState.engines.continuousKeystroke.getSampleCount();
    const minRequired = force ? 10 : AppState.monitoring.minKeystrokes;
    if (sampleCount < minRequired) {
        return; // Insufficient behavioral data
    }

    // Extract the 9 behavioral features and reset engine for the next window
    const features = AppState.engines.continuousKeystroke.getFeatures();
    AppState.engines.continuousKeystroke.reset();
    updateBufferUI(0);

    AppState.monitoring.evaluating = true;

    try {
        const result = await apiPost('/verification/features', {
            session_id: AppState.monitoring.sessionId,
            features: features
            // Note: typing_pattern is deliberately omitted to prevent continuous TypingDNA calls
        });

        handleMonitoringResult(result);
    } catch (err) {
        handleMonitoringError(err);
    } finally {
        AppState.monitoring.evaluating = false;
    }
}

/**
 * Process successful monitoring response from backend.
 * Updates risk score, risk level, action, gauge, top deviations, and history.
 */
function handleMonitoringResult(result) {
    if (!result) return;

    const riskScore = typeof result.risk_score === 'number' ? result.risk_score : 0.0;
    const riskLevel = result.risk_level || 'LOW';
    const action = result.action || 'CONTINUE';
    const confidence = typeof result.confidence === 'number' ? result.confidence : 0.65;
    const fusionMode = result.fusion_mode || 'LOCAL_ONLY';
    const topDeviations = result.top_anomalous_features || [];
    const now = new Date();
    const timeStr = now.toLocaleTimeString();

    AppState.monitoring.currentRisk = riskScore;
    AppState.monitoring.currentLevel = riskLevel;
    AppState.monitoring.lastVerification = timeStr;

    // 1. Record display history (max 20 entries)
    AppState.monitoring.history.unshift({
        timestamp: timeStr,
        score: riskScore.toFixed(1),
        level: riskLevel
    });
    if (AppState.monitoring.history.length > 20) {
        AppState.monitoring.history.pop();
    }

    // 2. Update Metric Cards
    const riskScoreSpan = document.getElementById('dash-risk-score');
    if (riskScoreSpan) {
        riskScoreSpan.textContent = `${riskScore.toFixed(1)} / 100`;
    }

    const riskBadge = document.getElementById('dash-risk-badge');
    if (riskBadge) {
        riskBadge.textContent = riskLevel;
        riskBadge.className = `metric-badge badge-${riskLevel.toLowerCase()}`;
    }

    const confVal = document.getElementById('dash-confidence-value');
    if (confVal) {
        confVal.textContent = `${Math.round(confidence * 100)}%`;
    }

    const modeVal = document.getElementById('dash-verification-mode');
    if (modeVal) {
        modeVal.textContent = fusionMode === 'ML_TYPINGDNA' ? 'ML + TYPINGDNA' : 'LOCAL ML';
    }

    const lastVerifSpan = document.getElementById('dash-last-verification');
    if (lastVerifSpan) {
        lastVerifSpan.textContent = `Last verification: ${timeStr}`;
    }

    // 3. Update Visual Risk Meter Gauge (0 -> 100)
    const gaugeNeedle = document.getElementById('risk-gauge-needle');
    const gaugeFill = document.getElementById('risk-gauge-fill');
    if (gaugeNeedle && gaugeFill) {
        const clampedScore = Math.max(0, Math.min(100, riskScore));
        gaugeNeedle.style.left = `${clampedScore}%`;
        gaugeFill.style.width = `${100 - clampedScore}%`;
    }

    // 4. Update Security Status & Action Behavior
    const statusBadge = document.getElementById('dash-status-badge');
    const statusSub = document.getElementById('dash-status-sub');
    const reauthBanner = document.getElementById('dash-reauth-banner');

    if (action === 'CONTINUE') {
        AppState.monitoring.reauthRequired = false;
        AppState.monitoring.status = 'SECURE';
        if (statusBadge) statusBadge.textContent = 'SECURE';
        if (statusSub) statusSub.textContent = 'Session protected by SentinelAI';
        if (reauthBanner) reauthBanner.style.display = 'none';
        setMonitoringIndicator('ACTIVE', 'LIVE MONITORING');
    } else if (action === 'MONITOR') {
        AppState.monitoring.reauthRequired = false;
        AppState.monitoring.status = 'MONITORING';
        if (statusBadge) statusBadge.textContent = 'ELEVATED RISK';
        if (statusSub) statusSub.textContent = 'Mild anomaly detected — monitoring closely';
        if (reauthBanner) reauthBanner.style.display = 'none';
        setMonitoringIndicator('ACTIVE', 'LIVE MONITORING');
    } else if (action === 'REAUTHENTICATE') {
        AppState.monitoring.reauthRequired = true;
        AppState.monitoring.status = 'REAUTHENTICATION REQUIRED';
        if (statusBadge) statusBadge.textContent = 'RE-AUTH REQUIRED';
        if (statusSub) statusSub.textContent = 'Elevated behavioral anomaly detected';
        if (reauthBanner) reauthBanner.style.display = 'flex';
        setMonitoringIndicator('PAUSED', 'RE-AUTH REQUIRED');
        showNotification('Additional verification required: Elevated behavioral anomaly detected.', 'warning');
    } else if (action === 'LOCK_SESSION' || riskLevel === 'CRITICAL') {
        AppState.monitoring.reauthRequired = false;
        AppState.monitoring.status = 'SESSION LOCKED';
        if (statusBadge) statusBadge.textContent = 'LOCKED';
        if (statusSub) statusSub.textContent = 'Session locked due to critical risk';
        setMonitoringIndicator('LOCKED', 'SESSION LOCKED');

        // Immediately stop continuous monitoring and present the locked view
        stopContinuousMonitoring();
        handleSessionLock('Critical behavioral anomaly detected (Risk Score >= 80).');
        return;
    }

    // 5. Update "Why did my risk change?" Top Anomalous Features Panel
    updateAnomalousFeaturesUI(topDeviations);

    // 6. Update Risk History Table
    updateHistoryTableUI();
}

/**
 * Render the "Why did my risk change?" top anomalous features panel.
 */
function updateAnomalousFeaturesUI(deviations) {
    const panel = document.getElementById('dash-anomalous-features-panel');
    if (!panel) return;

    if (!deviations || deviations.length === 0) {
        panel.innerHTML = `
            <div class="empty-deviation-state">
                No significant behavioral deviations detected. Typing rhythm matches established baseline.
            </div>
        `;
        return;
    }

    // Check if any deviation is noteworthy (>= 1.5 standard deviations)
    const notable = deviations.filter(d => (d.deviation || 0) >= 1.2);
    if (notable.length === 0) {
        panel.innerHTML = `
            <div class="empty-deviation-state">
                Behavioral features are within normal variance of your baseline profile.
            </div>
        `;
        return;
    }

    const featureLabels = {
        typing_speed: 'Typing Tempo (Speed)',
        mean_hold_time: 'Key Hold Duration',
        std_hold_time: 'Hold Duration Consistency',
        mean_flight_time: 'Inter-Key Flight Time',
        std_flight_time: 'Flight Rhythm Consistency',
        backspace_rate: 'Correction / Backspace Frequency',
        pause_mean: 'Hesitation & Pause Duration',
        mouse_velocity_mean: 'Mouse Movement Speed',
        click_interval_mean: 'Click Interval Rhythm'
    };

    const friendlyExplanations = {
        typing_speed: 'Typing cadence is noticeably faster or slower than your enrolled baseline.',
        mean_hold_time: 'Keys are being held down for a different duration than your normal rhythm.',
        std_hold_time: 'Key pressing duration is less consistent than your typical habit.',
        mean_flight_time: 'Time gap between releasing one key and pressing the next deviates from baseline rhythm.',
        std_flight_time: 'Rhythm transitions between keys show unusual variation compared to baseline.',
        backspace_rate: 'Unusually high or low correction rate detected compared to normal baseline.',
        pause_mean: 'Hesitation pauses between words differ from your typical typing flow.'
    };

    let html = '';
    notable.forEach(item => {
        const name = featureLabels[item.feature] || item.feature;
        const devVal = (item.deviation || 0).toFixed(1);
        const isHigh = item.deviation >= 2.5;
        const explain = friendlyExplanations[item.feature] || item.explanation || 'Behavior deviates from established baseline';

        html += `
            <div class="anomalous-feature-item ${isHigh ? 'high-dev' : ''}">
                <div class="feature-header-row">
                    <span class="feature-name">${escapeHtml(name)}</span>
                    <span class="feature-dev-badge ${isHigh ? 'high-dev' : ''}">+${devVal}&sigma; deviation</span>
                </div>
                <div class="feature-explain-text">${escapeHtml(explain)}</div>
            </div>
        `;
    });

    panel.innerHTML = html;
}

/**
 * Render the recent risk history table on the dashboard.
 */
function updateHistoryTableUI() {
    const tbody = document.getElementById('dash-history-list');
    if (!tbody) return;

    const history = AppState.monitoring.history;
    if (!history || history.length === 0) {
        tbody.innerHTML = `
            <tr class="empty-history-row">
                <td colspan="3">Awaiting first feature window...</td>
            </tr>
        `;
        return;
    }

    let html = '';
    history.forEach(item => {
        const badgeClass = `badge-${item.level.toLowerCase()}`;
        html += `
            <tr>
                <td class="history-time">${escapeHtml(item.timestamp)}</td>
                <td class="history-score">${escapeHtml(item.score)}</td>
                <td><span class="metric-badge ${badgeClass}">${escapeHtml(item.level)}</span></td>
            </tr>
        `;
    });

    tbody.innerHTML = html;
}

/**
 * Handle network or transient errors during feature submissions.
 * Does not fabricate scores; pauses monitoring cleanly with a safe backoff delay.
 */
function handleMonitoringError(err) {
    console.warn('Continuous monitoring evaluation error:', err);

    // If session was locked or not active on backend
    if (err.message && (err.message.includes('not active') || err.message.includes('LOCKED'))) {
        stopContinuousMonitoring();
        handleSessionLock('Verification session was locked by the security engine.');
        return;
    }

    // Network interruption: do NOT lock the user or fabricate a score
    setMonitoringIndicator('PAUSED', 'CONNECTION PAUSED');
    showNotification('Connection interrupted — monitoring temporarily paused.', 'warning');
    AppState.monitoring.pauseUntil = Date.now() + 5000; // 5s backoff
}

/**
 * Update the visual live monitoring indicator badge.
 * Supported states: 'ACTIVE', 'PAUSED', 'LOCKED', 'ERROR'.
 */
function setMonitoringIndicator(state, text) {
    const dot = document.getElementById('indicator-dot');
    const label = document.getElementById('indicator-text');
    if (!dot || !label) return;

    dot.className = `indicator-dot ${state.toLowerCase()}`;
    label.textContent = text;
}

/**
 * Update the keystroke window buffer counter on the dashboard sandbox.
 */
function updateBufferUI(count) {
    const bufferSpan = document.getElementById('dash-buffer-count');
    if (bufferSpan) {
        bufferSpan.innerHTML = `Window buffer: <strong>${count} / ${MIN_WINDOW_KEYSTROKES}</strong> keystrokes`;
    }
}


// =====================================================================
// Session Locking & Re-authentication Handlers
// =====================================================================

function handleSessionLock(reason = null) {
    stopContinuousMonitoring();

    const reasonEl = document.getElementById('locked-reason-text');
    if (reasonEl && reason) {
        reasonEl.textContent = reason;
    }

    const emailInput = document.getElementById('unlock-email');
    if (emailInput && AppState.user) {
        emailInput.value = AppState.user.email || '';
    }

    const pwdInput = document.getElementById('unlock-password');
    if (pwdInput) {
        pwdInput.value = '';
    }

    showLocked(reason);
}

function setupLockedView(reason) {
    const emailInput = document.getElementById('unlock-email');
    if (emailInput && AppState.user) {
        emailInput.value = AppState.user.email || '';
    }

    // Default to password tab
    switchUnlockTab('pwd');

    // Setup biometric unlock engine for the phrase input
    const unlockInput = document.getElementById('unlock-phrase-input');
    if (unlockInput) {
        unlockInput.value = '';

        if (!AppState.engines.unlockKeystroke && window.SentinelKeystrokeEngine) {
            AppState.engines.unlockKeystroke = new window.SentinelKeystrokeEngine({
                targetElement: unlockInput
            });
        }
        if (!AppState.engines.unlockTypingdna && window.TypingDNAClient) {
            AppState.engines.unlockTypingdna = new window.TypingDNAClient({
                targetElement: unlockInput
            });
        }

        if (AppState.engines.unlockKeystroke) {
            AppState.engines.unlockKeystroke.start(unlockInput);
        }
        if (AppState.engines.unlockTypingdna) {
            AppState.engines.unlockTypingdna.start(unlockInput);
        }
    }
}

function switchUnlockTab(tab) {
    const btnPwd = document.getElementById('tab-unlock-pwd');
    const btnBio = document.getElementById('tab-unlock-bio');
    const formPwd = document.getElementById('form-unlock-password');
    const formBio = document.getElementById('form-unlock-biometric');

    if (tab === 'pwd') {
        if (btnPwd) btnPwd.classList.add('active');
        if (btnBio) btnBio.classList.remove('active');
        if (formPwd) formPwd.style.display = 'block';
        if (formBio) formBio.style.display = 'none';
    } else {
        if (btnPwd) btnPwd.classList.remove('active');
        if (btnBio) btnBio.classList.add('active');
        if (formPwd) formPwd.style.display = 'none';
        if (formBio) formBio.style.display = 'block';
    }
}

/**
 * Clear any outstanding re-authentication requirement after a successful
 * biometric or password verification, restoring the normal live-monitoring UI
 * while preserving the actual behavioral risk score and history.
 */
function clearReauthRequirement() {
    AppState.monitoring.reauthRequired = false;

    const reauthBanner = document.getElementById('dash-reauth-banner');
    if (reauthBanner) {
        reauthBanner.style.display = 'none';
    }

    const statusBadge = document.getElementById('dash-status-badge');
    const statusSub = document.getElementById('dash-status-sub');
    if (statusBadge) {
        statusBadge.textContent = 'SECURE';
    }
    if (statusSub) {
        statusSub.textContent = 'Identity verified — session protected by SentinelAI';
    }
    AppState.monitoring.status = 'SECURE';

    setMonitoringIndicator('ACTIVE', 'LIVE MONITORING');
}

/**
 * Handle password re-authentication to unlock session.
 * Calls existing backend POST /auth/reauthenticate with { session_id, email, password }.
 */
async function handlePasswordUnlock(password) {
    if (!AppState.monitoring.sessionId) {
        showNotification('No active session ID found. Please log in again.', 'error');
        showView('login');
        return;
    }
    if (!AppState.user || !AppState.user.email) {
        showNotification('User email missing. Please log in again.', 'error');
        showView('login');
        return;
    }

    try {
        const result = await apiPost('/auth/reauthenticate', {
            session_id: AppState.monitoring.sessionId,
            email: AppState.user.email,
            password: password
        });

        if (result.status === 'VERIFIED') {
            showNotification('Session unlocked successfully. Access restored!', 'success');
            clearReauthRequirement();
            showDashboard();
            startContinuousMonitoring();
        } else {
            showNotification('Re-authentication could not be confirmed.', 'error');
        }
    } catch (err) {
        showNotification(err.message || 'Re-authentication failed. Incorrect password.', 'error');
    }
}

/**
 * Handle biometric checkpoint verification to unlock session.
 * Reuses existing backend POST /verification/checkpoint with { session_id, features, typing_pattern }.
 */
async function handleBiometricUnlock() {
    if (!AppState.monitoring.sessionId) {
        showNotification('No active session ID found. Please log in again.', 'error');
        showView('login');
        return;
    }

    const inputEl = document.getElementById('unlock-phrase-input');
    if (!inputEl) return;

    const typedText = inputEl.value.trim().toLowerCase();
    if (typedText !== ENROLLMENT_PHRASE) {
        showNotification('Please type the exact verification phrase.', 'warning');
        return;
    }

    if (!AppState.engines.unlockKeystroke) {
        showNotification('Keystroke engine not initialized.', 'error');
        return;
    }

    const features = AppState.engines.unlockKeystroke.getFeatures();
    let pattern = "";
    if (AppState.engines.unlockTypingdna) {
        pattern = AppState.engines.unlockTypingdna.getTypingPattern({
            type: 2,
            text: ENROLLMENT_PHRASE,
            targetId: 'unlock-phrase-input'
        });
    }

    try {
        const result = await apiPost('/verification/checkpoint', {
            session_id: AppState.monitoring.sessionId,
            features: features,
            typing_pattern: pattern
        });

        if (result.risk_level === 'LOW' || result.risk_level === 'MEDIUM') {
            showNotification('Biometric identity confirmed! Session restored to ACTIVE.', 'success');
            clearReauthRequirement();
            showDashboard();
            startContinuousMonitoring();
        } else {
            showNotification(`Biometric verification failed (Risk: ${result.risk_level}). Session remains locked.`, 'error');
        }
    } catch (err) {
        showNotification(err.message || 'Biometric verification failed.', 'error');
    }
}


// =====================================================================
// Dashboard Shell Helpers
// =====================================================================

function updateDashboardShell() {
    if (!AppState.user) return;

    const userEmailSpan = document.getElementById('dash-user-email');
    if (userEmailSpan) {
        userEmailSpan.textContent = AppState.user.email;
    }

    const userDisplaySpan = document.getElementById('user-display-name');
    if (userDisplaySpan) {
        userDisplaySpan.textContent = AppState.user.name || AppState.user.email || 'User';
    }
}


// =====================================================================
// Startup & DOM Event Wiring
// =====================================================================

document.addEventListener('DOMContentLoaded', async () => {
    // 1. Wire Login Form
    const loginForm = document.getElementById('form-login');
    if (loginForm) {
        loginForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const email = document.getElementById('login-email').value;
            const password = document.getElementById('login-password').value;
            loginUser(email, password);
        });
    }

    // 2. Wire Register Form
    const registerForm = document.getElementById('form-register');
    if (registerForm) {
        registerForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const name = document.getElementById('register-name').value;
            const email = document.getElementById('register-email').value;
            const password = document.getElementById('register-password').value;
            registerUser(name, email, password);
        });
    }

    // 3. Wire Navigation / Switch links
    const toRegisterLink = document.getElementById('link-to-register');
    if (toRegisterLink) {
        toRegisterLink.addEventListener('click', (e) => {
            e.preventDefault();
            showRegister();
        });
    }

    const toLoginLink = document.getElementById('link-to-login');
    if (toLoginLink) {
        toLoginLink.addEventListener('click', (e) => {
            e.preventDefault();
            showLogin();
        });
    }

    const logoutBtn = document.getElementById('btn-logout');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', (e) => {
            e.preventDefault();
            logoutUser();
        });
    }

    const lockedLogoutLink = document.getElementById('link-locked-logout');
    if (lockedLogoutLink) {
        lockedLogoutLink.addEventListener('click', (e) => {
            e.preventDefault();
            logoutUser();
        });
    }

    // 4. Wire Enrollment Submission
    const submitSampleBtn = document.getElementById('btn-submit-sample');
    if (submitSampleBtn) {
        submitSampleBtn.addEventListener('click', (e) => {
            e.preventDefault();
            submitEnrollmentSample();
        });
    }

    const enrollInput = document.getElementById('enroll-input');
    if (enrollInput) {
        enrollInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                submitEnrollmentSample();
            }
        });
    }

    const phraseDisplay = document.getElementById('phrase-display-text');
    if (phraseDisplay) {
        phraseDisplay.textContent = ENROLLMENT_PHRASE;
    }

    // 5. Wire Continuous Monitoring Interactive Sandbox
    const sandboxTextarea = document.getElementById('dash-typing-sandbox');
    if (sandboxTextarea) {
        sandboxTextarea.addEventListener('input', () => {
            if (!AppState.monitoring.active || !AppState.engines.continuousKeystroke) return;
            const count = AppState.engines.continuousKeystroke.getSampleCount();
            updateBufferUI(count);

            if (count >= MIN_WINDOW_KEYSTROKES && !AppState.monitoring.evaluating) {
                submitFeatureWindow();
            }
        });
    }

    const btnForceEvaluate = document.getElementById('btn-force-evaluate');
    if (btnForceEvaluate) {
        btnForceEvaluate.addEventListener('click', (e) => {
            e.preventDefault();
            if (!AppState.engines.continuousKeystroke) return;
            const count = AppState.engines.continuousKeystroke.getSampleCount();
            if (count >= 10) {
                submitFeatureWindow(true);
            } else {
                showNotification(`Please type at least 10 keystrokes before manual evaluation (current: ${count}).`, 'warning');
            }
        });
    }

    // Global Keyup Listener for Dashboard Window Buffer Tracking
    window.addEventListener('keyup', () => {
        if (AppState.currentView === 'dashboard' && AppState.monitoring.active && AppState.engines.continuousKeystroke) {
            const count = AppState.engines.continuousKeystroke.getSampleCount();
            updateBufferUI(count);

            if (count >= MIN_WINDOW_KEYSTROKES && !AppState.monitoring.evaluating) {
                submitFeatureWindow();
            }
        }
    });

    // 6. Wire Re-authentication Banner Checkpoint Trigger
    const btnTriggerCheckpoint = document.getElementById('btn-trigger-checkpoint');
    if (btnTriggerCheckpoint) {
        btnTriggerCheckpoint.addEventListener('click', () => {
            handleSessionLock('Manual biometric verification requested.');
        });
    }

    // 7. Wire Unlock Tabs & Forms
    const tabUnlockPwd = document.getElementById('tab-unlock-pwd');
    if (tabUnlockPwd) {
        tabUnlockPwd.addEventListener('click', () => switchUnlockTab('pwd'));
    }

    const tabUnlockBio = document.getElementById('tab-unlock-bio');
    if (tabUnlockBio) {
        tabUnlockBio.addEventListener('click', () => switchUnlockTab('bio'));
    }

    const formUnlockPwd = document.getElementById('form-unlock-password');
    if (formUnlockPwd) {
        formUnlockPwd.addEventListener('submit', (e) => {
            e.preventDefault();
            const password = document.getElementById('unlock-password').value;
            handlePasswordUnlock(password);
        });
    }

    const btnUnlockBio = document.getElementById('btn-unlock-biometric-submit');
    if (btnUnlockBio) {
        btnUnlockBio.addEventListener('click', () => {
            handleBiometricUnlock();
        });
    }

    // 8. Restore Saved Session from localStorage
    const savedToken = localStorage.getItem('sentinelai_token');
    const savedUser = localStorage.getItem('sentinelai_user');

    if (savedToken && savedUser) {
        try {
            AppState.token = savedToken;
            AppState.user = JSON.parse(savedUser);
            await checkEnrollmentAndRoute();
        } catch (e) {
            localStorage.removeItem('sentinelai_token');
            localStorage.removeItem('sentinelai_user');
            showLogin();
        }
    } else {
        showLogin();
    }
});

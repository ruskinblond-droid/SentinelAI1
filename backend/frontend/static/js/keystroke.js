/**
 * SentinelAI — Client-Side Keystroke Dynamics & 9-Feature Behavioral Engine
 *
 * Captures keystroke timing and mouse dynamics locally in the browser
 * and calculates the official SentinelAI 9-feature behavioral vector.
 *
 * Privacy Notice:
 * - Only timing intervals, counts, and statistical metrics are retained.
 * - Raw typed text, characters, and passwords are NEVER captured or stored.
 *
 * Feature Contract (9 numerical features):
 * 1. typing_speed: keystrokes/characters per minute
 * 2. mean_hold_time: average duration key is held down (ms)
 * 3. std_hold_time: standard deviation of hold durations (ms)
 * 4. mean_flight_time: average interval between key release and next key press (ms)
 * 5. std_flight_time: standard deviation of flight times (ms)
 * 6. backspace_rate: backspace presses divided by total key presses
 * 7. pause_mean: average duration of long pauses between keystrokes (ms)
 * 8. mouse_velocity_mean: average mouse velocity (pixels/ms)
 * 9. click_interval_mean: average interval between mouse clicks (ms)
 */

(function (root, factory) {
    if (typeof module === 'object' && module.exports) {
        // Node / CommonJS
        module.exports = factory();
    } else {
        // Browser globals
        const engine = factory();
        root.SentinelKeystrokeEngine = engine;
        root.KeystrokeEngine = engine;
    }
}(typeof self !== 'undefined' ? self : this, function () {

    const DEFAULT_PAUSE_THRESHOLD_MS = 250.0; // Interval >= 250ms considered a pause
    const MAX_PLAUSIBLE_HOLD_TIME_MS = 3000.0; // Filter out keys stuck during window blur
    const MAX_PLAUSIBLE_FLIGHT_TIME_MS = 15000.0; // Filter out long idle periods from flight times

    class SentinelKeystrokeEngine {
        /**
         * @param {Object} [options]
         * @param {HTMLElement|null} [options.targetElement=null] - Specific input/textarea to monitor, or null for window
         * @param {number} [options.pauseThresholdMs=250.0] - Threshold in ms to qualify as a typing pause
         * @param {boolean} [options.listenMouse=true] - Whether to capture mouse dynamics
         */
        constructor(options = {}) {
            this.targetElement = options.targetElement || null;
            this.pauseThresholdMs = options.pauseThresholdMs || DEFAULT_PAUSE_THRESHOLD_MS;
            this.listenMouse = options.listenMouse !== false;

            this._active = false;

            // Internal timing tracking
            this.activeKeypresses = new Map(); // code -> timestamp
            this.holdTimes = []; // ms
            this.flightTimes = []; // ms
            this.pauses = []; // ms
            this.totalKeyPressCount = 0;
            this.backspaceCount = 0;

            this.firstKeyDownTime = 0;
            this.lastKeyDownTime = 0;
            this.lastKeyUpTime = 0;
            this.lastActivityTime = 0;

            // Mouse tracking
            this.mouseVelocities = []; // px/ms
            this.clickIntervals = []; // ms
            this.lastMousePos = null; // {x, y, t}
            this.lastClickTime = 0;

            // Bound event listener references for clean attach/detach
            this._onKeyDown = this._handleKeyDown.bind(this);
            this._onKeyUp = this._handleKeyUp.bind(this);
            this._onMouseMove = this._handleMouseMove.bind(this);
            this._onClick = this._handleClick.bind(this);
            this._onBlur = this._handleBlur.bind(this);
        }

        /**
         * Get high-resolution timestamp in milliseconds
         * @returns {number}
         */
        _now() {
            if (typeof performance !== 'undefined' && performance.now) {
                return performance.now();
            }
            return Date.now();
        }

        /**
         * Start capturing behavioral events
         * @param {HTMLElement|null} [newTargetElement] - Optional DOM element to bind to
         */
        start(newTargetElement = null) {
            if (newTargetElement) {
                this.targetElement = newTargetElement;
            }

            if (this._active) {
                return; // Idempotent: already running
            }

            this._active = true;

            const target = this.targetElement || (typeof window !== 'undefined' ? window : null);
            if (!target) return;

            // Keyboard listeners (passive to ensure zero interference with input or TypingDNA)
            target.addEventListener('keydown', this._onKeyDown, false);
            target.addEventListener('keyup', this._onKeyUp, false);

            if (typeof window !== 'undefined') {
                window.addEventListener('blur', this._onBlur, false);

                // Mouse listeners attached to window for global movement awareness
                if (this.listenMouse) {
                    window.addEventListener('mousemove', this._onMouseMove, { passive: true });
                    window.addEventListener('mousedown', this._onClick, { passive: true });
                }
            }
        }

        /**
         * Stop capturing behavioral events
         */
        stop() {
            if (!this._active) {
                return; // Idempotent: already stopped
            }

            this._active = false;
            this.activeKeypresses.clear();

            const target = this.targetElement || (typeof window !== 'undefined' ? window : null);
            if (target) {
                target.removeEventListener('keydown', this._onKeyDown, false);
                target.removeEventListener('keyup', this._onKeyUp, false);
            }

            if (typeof window !== 'undefined') {
                window.removeEventListener('blur', this._onBlur, false);
                if (this.listenMouse) {
                    window.removeEventListener('mousemove', this._onMouseMove);
                    window.removeEventListener('mousedown', this._onClick);
                }
            }
        }

        /**
         * Reset all collected samples, counters, and timers
         */
        reset() {
            this.activeKeypresses.clear();
            this.holdTimes = [];
            this.flightTimes = [];
            this.pauses = [];
            this.totalKeyPressCount = 0;
            this.backspaceCount = 0;

            this.firstKeyDownTime = 0;
            this.lastKeyDownTime = 0;
            this.lastKeyUpTime = 0;
            this.lastActivityTime = 0;

            this.mouseVelocities = [];
            this.clickIntervals = [];
            this.lastMousePos = null;
            this.lastClickTime = 0;
        }

        /**
         * Check if engine is currently capturing
         * @returns {boolean}
         */
        isRunning() {
            return this._active;
        }

        /**
         * Total valid keystrokes registered in current session
         * @returns {number}
         */
        getSampleCount() {
            return this.totalKeyPressCount;
        }

        // ========================================================
        // Event Handlers
        // ========================================================

        _handleKeyDown(event) {
            if (!this._active) return;

            // Ignore OS key auto-repeat when key is held down
            if (event.repeat) return;

            const now = this._now();
            const code = event.code || event.key || 'UnknownKey';

            if (!this.firstKeyDownTime) {
                this.firstKeyDownTime = now;
            }

            // Calculate flight time: gap between previous keyup and current keydown
            if (this.lastKeyUpTime > 0) {
                const flightTime = now - this.lastKeyUpTime;
                if (flightTime >= 0 && flightTime <= MAX_PLAUSIBLE_FLIGHT_TIME_MS) {
                    this.flightTimes.push(flightTime);

                    // Check if interval meets pause definition
                    if (flightTime >= this.pauseThresholdMs) {
                        this.pauses.push(flightTime);
                    }
                }
            }

            // Track backspaces without recording sensitive content
            if (event.key === 'Backspace' || code === 'Backspace') {
                this.backspaceCount++;
            }

            this.totalKeyPressCount++;
            this.lastKeyDownTime = now;
            this.lastActivityTime = now;

            // Record keydown timestamp for hold time pairing
            this.activeKeypresses.set(code, now);
        }

        _handleKeyUp(event) {
            if (!this._active) return;

            const now = this._now();
            const code = event.code || event.key || 'UnknownKey';

            // Match keyup with active keydown
            if (this.activeKeypresses.has(code)) {
                const downTime = this.activeKeypresses.get(code);
                const holdTime = now - downTime;

                if (holdTime >= 0 && holdTime <= MAX_PLAUSIBLE_HOLD_TIME_MS) {
                    this.holdTimes.push(holdTime);
                }

                this.activeKeypresses.delete(code);
                this.lastKeyUpTime = now;
                this.lastActivityTime = now;
            }
        }

        _handleMouseMove(event) {
            if (!this._active) return;

            const now = this._now();
            const currentX = event.clientX;
            const currentY = event.clientY;

            if (this.lastMousePos) {
                const dt = now - this.lastMousePos.t;
                if (dt > 5 && dt < 1000) { // filter out instant or stale intervals
                    const dx = currentX - this.lastMousePos.x;
                    const dy = currentY - this.lastMousePos.y;
                    const distance = Math.sqrt(dx * dx + dy * dy);
                    const velocity = distance / dt; // pixels per ms

                    // Filter out extreme velocity spikes (e.g. pointer lock teleportation)
                    if (velocity < 50.0) {
                        this.mouseVelocities.push(velocity);
                    }
                }
            }

            this.lastMousePos = { x: currentX, y: currentY, t: now };
        }

        _handleClick(event) {
            if (!this._active) return;

            const now = this._now();

            if (this.lastClickTime > 0) {
                const interval = now - this.lastClickTime;
                if (interval > 10 && interval < 10000) {
                    this.clickIntervals.push(interval);
                }
            }

            this.lastClickTime = now;
        }

        _handleBlur() {
            // When window/tab loses focus, clear pending keypresses to prevent inflated hold times
            this.activeKeypresses.clear();
            this.lastMousePos = null;
        }

        // ========================================================
        // Statistical Computations
        // ========================================================

        _calcMean(arr) {
            if (!arr || arr.length === 0) return 0.0;
            const sum = arr.reduce((acc, val) => acc + val, 0);
            return sum / arr.length;
        }

        _calcStd(arr, mean = null) {
            if (!arr || arr.length < 2) return 0.0;
            const m = mean !== null ? mean : this._calcMean(arr);
            const variance = arr.reduce((acc, val) => acc + Math.pow(val - m, 2), 0) / arr.length;
            return Math.sqrt(variance);
        }

        _cleanNumber(val, decimals = 2) {
            if (val === null || val === undefined || isNaN(val) || !isFinite(val)) {
                return 0.0;
            }
            const factor = Math.pow(10, decimals);
            return Math.round(val * factor) / factor;
        }

        // ========================================================
        // 9-Feature Vector Generation
        // ========================================================

        /**
         * Calculate and return SentinelAI's 9-feature behavioral vector.
         * Guaranteed to return all 9 fields as clean, finite numbers.
         *
         * @returns {Object}
         */
        getFeatures() {
            // 1. typing_speed: total keystrokes per minute
            let typingSpeed = 0.0;
            const totalDurationMs = (this.lastActivityTime > this.firstKeyDownTime)
                ? (this.lastActivityTime - this.firstKeyDownTime)
                : 0;

            if (totalDurationMs > 0 && this.totalKeyPressCount > 0) {
                const durationMinutes = totalDurationMs / 60000.0;
                typingSpeed = this.totalKeyPressCount / durationMinutes;
            }

            // 2. mean_hold_time & 3. std_hold_time
            const meanHoldTime = this._calcMean(this.holdTimes);
            const stdHoldTime = this._calcStd(this.holdTimes, meanHoldTime);

            // 4. mean_flight_time & 5. std_flight_time
            const meanFlightTime = this._calcMean(this.flightTimes);
            const stdFlightTime = this._calcStd(this.flightTimes, meanFlightTime);

            // 6. backspace_rate
            let backspaceRate = 0.0;
            if (this.totalKeyPressCount > 0) {
                backspaceRate = this.backspaceCount / this.totalKeyPressCount;
            }

            // 7. pause_mean
            const pauseMean = this._calcMean(this.pauses);

            // 8. mouse_velocity_mean
            const mouseVelocityMean = this._calcMean(this.mouseVelocities);

            // 9. click_interval_mean
            const clickIntervalMean = this._calcMean(this.clickIntervals);

            return {
                typing_speed: this._cleanNumber(typingSpeed, 2),
                mean_hold_time: this._cleanNumber(meanHoldTime, 2),
                std_hold_time: this._cleanNumber(stdHoldTime, 2),
                mean_flight_time: this._cleanNumber(meanFlightTime, 2),
                std_flight_time: this._cleanNumber(stdFlightTime, 2),
                backspace_rate: this._cleanNumber(backspaceRate, 4),
                pause_mean: this._cleanNumber(pauseMean, 2),
                mouse_velocity_mean: this._cleanNumber(mouseVelocityMean, 4),
                click_interval_mean: this._cleanNumber(clickIntervalMean, 2)
            };
        }
    }

    return SentinelKeystrokeEngine;
}));

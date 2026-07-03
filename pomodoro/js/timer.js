/* ============================================
   PomodoroTimer — Timer Core Logic
   ============================================ */

class PomodoroTimer {
  constructor() {
    this._totalSeconds = 0;
    this._remainingSeconds = 0;
    this._intervalId = null;
    this._isRunning = false;
    this._listeners = {};
  }

  /**
   * Set the timer duration and reset to idle state.
   * @param {number} minutes
   */
  setDuration(minutes) {
    this._totalSeconds = minutes * 60;
    this._remainingSeconds = this._totalSeconds;
    this._isRunning = false;
    this._clearInterval();
  }

  /**
   * Start or resume the timer.
   */
  start() {
    if (this._isRunning) return;
    if (this._remainingSeconds <= 0) return;

    this._isRunning = true;
    this._emit('start');

    this._intervalId = setInterval(() => {
      this._remainingSeconds--;

      this._emit('tick', {
        remaining: this._remainingSeconds,
        total: this._totalSeconds,
        progress: 1 - this._remainingSeconds / this._totalSeconds
      });

      if (this._remainingSeconds <= 0) {
        this._isRunning = false;
        this._clearInterval();
        this._emit('finish');
      }
    }, 1000);
  }

  /**
   * Pause the timer without resetting.
   */
  pause() {
    if (!this._isRunning) return;
    this._isRunning = false;
    this._clearInterval();
    this._emit('pause');
  }

  /**
   * Toggle between start and pause.
   */
  toggle() {
    if (this._isRunning) {
      this.pause();
    } else {
      this.start();
    }
  }

  /**
   * Reset the timer to its full duration (idle state).
   */
  reset() {
    const wasRunning = this._isRunning;
    this._isRunning = false;
    this._clearInterval();
    this._remainingSeconds = this._totalSeconds;
    this._emit('reset', {
      remaining: this._remainingSeconds,
      total: this._totalSeconds,
      progress: 0
    });
    if (wasRunning) {
      this._emit('pause');
    }
  }

  /**
   * Skip to the end (set remaining to 0, fire finish).
   */
  skip() {
    this._isRunning = false;
    this._clearInterval();
    this._remainingSeconds = 0;
    this._emit('tick', {
      remaining: 0,
      total: this._totalSeconds,
      progress: 1
    });
    this._emit('finish');
  }

  /**
   * Get current state.
   */
  getState() {
    return {
      totalSeconds: this._totalSeconds,
      remainingSeconds: this._remainingSeconds,
      isRunning: this._isRunning,
      progress: this._totalSeconds > 0
        ? 1 - this._remainingSeconds / this._totalSeconds
        : 0
    };
  }

  /**
   * Event emitter.
   */
  on(event, callback) {
    if (!this._listeners[event]) {
      this._listeners[event] = [];
    }
    this._listeners[event].push(callback);
  }

  _emit(event, data) {
    if (this._listeners[event]) {
      for (const cb of this._listeners[event]) {
        cb(data);
      }
    }
  }

  _clearInterval() {
    if (this._intervalId !== null) {
      clearInterval(this._intervalId);
      this._intervalId = null;
    }
  }
}

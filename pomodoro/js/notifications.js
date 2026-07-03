/* ============================================
   Notifications — Sound & Desktop Notifications
   ============================================ */

const Notifications = (() => {
  let audioCtx = null;
  let volume = 0.7;

  function getContext() {
    if (!audioCtx) {
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
    // Resume if suspended (browser autoplay policy)
    if (audioCtx.state === 'suspended') {
      audioCtx.resume();
    }
    return audioCtx;
  }

  /**
   * Set volume (0.0 - 1.0).
   */
  function setVolume(vol) {
    volume = Math.max(0, Math.min(1, vol));
  }

  /**
   * Play a simple chime using Web Audio API.
   * @param {'workEnd'|'breakEnd'|'tick'} type
   */
  function playSound(type = 'workEnd') {
    try {
      const ctx = getContext();
      const now = ctx.currentTime;

      const sequences = {
        // Pomodoro complete — four ascending notes
        workEnd: [
          { freq: 523.25, start: 0,    dur: 0.15 },  // C5
          { freq: 659.25, start: 0.15, dur: 0.15 },  // E5
          { freq: 783.99, start: 0.3,  dur: 0.15 },  // G5
          { freq: 1046.5, start: 0.45, dur: 0.4  },  // C6
        ],
        // Break end — two gentle notes
        breakEnd: [
          { freq: 587.33, start: 0,    dur: 0.15 },  // D5
          { freq: 783.99, start: 0.15, dur: 0.3  },  // G5
        ],
        // Tick (last 5 seconds)
        tick: [
          { freq: 440, start: 0, dur: 0.08 },  // A4
        ],
      };

      const notes = sequences[type] || sequences.workEnd;

      for (const note of notes) {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();

        osc.type = type === 'tick' ? 'square' : 'sine';
        osc.frequency.setValueAtTime(note.freq, now + note.start);

        gain.gain.setValueAtTime(volume * 0.3, now + note.start);
        gain.gain.exponentialRampToValueAtTime(0.001, now + note.start + note.dur);

        osc.connect(gain);
        gain.connect(ctx.destination);

        osc.start(now + note.start);
        osc.stop(now + note.start + note.dur);
      }
    } catch (e) {
      // Audio not available — silently ignore
      console.warn('Sound playback failed:', e);
    }
  }

  /**
   * Show a desktop notification.
   * @param {string} title
   * @param {object} [options]
   */
  function showNotification(title, { body = '', icon = '🍅' } = {}) {
    if (!('Notification' in window)) return;

    if (Notification.permission === 'granted') {
      new Notification(title, { body, icon });
    }
  }

  /**
   * Request notification permission.
   */
  function requestPermission() {
    if (!('Notification' in window)) return;
    if (Notification.permission === 'default') {
      Notification.requestPermission();
    }
  }

  return {
    playSound,
    showNotification,
    requestPermission,
    setVolume,
  };
})();

/* ============================================
   Settings — Persistence & UI Binding
   ============================================ */

const SETTINGS_KEY = 'pomodoro-settings';

const DEFAULTS = {
  workDuration: 25,
  shortBreakDuration: 5,
  longBreakDuration: 15,
  longBreakInterval: 4,
  soundVolume: 70,
  autoStartBreaks: true,
  autoStartWork: true,
  theme: 'auto', // 'auto' | 'light' | 'dark'
};

const Settings = (() => {
  let _settings = { ...DEFAULTS };

  /**
   * Load settings from LocalStorage, merging with defaults.
   */
  function load() {
    try {
      const raw = localStorage.getItem(SETTINGS_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        _settings = { ...DEFAULTS, ...parsed };
      }
    } catch (e) {
      _settings = { ...DEFAULTS };
    }
    return _settings;
  }

  /**
   * Save current settings to LocalStorage.
   */
  function save() {
    try {
      localStorage.setItem(SETTINGS_KEY, JSON.stringify(_settings));
    } catch (e) {
      console.warn('Failed to save settings:', e);
    }
  }

  /**
   * Get a setting value.
   */
  function get(key) {
    return _settings[key] ?? DEFAULTS[key];
  }

  /**
   * Set a setting value and save.
   */
  function set(key, value) {
    _settings[key] = value;
    save();
  }

  /**
   * Bind the settings modal UI elements.
   * Returns an object with method to apply theme.
   */
  function bindUI() {
    const elements = {
      workDuration: document.getElementById('workDuration'),
      workDurationVal: document.getElementById('workDurationVal'),
      shortBreakDuration: document.getElementById('shortBreakDuration'),
      shortBreakDurationVal: document.getElementById('shortBreakDurationVal'),
      longBreakDuration: document.getElementById('longBreakDuration'),
      longBreakDurationVal: document.getElementById('longBreakDurationVal'),
      longBreakInterval: document.getElementById('longBreakInterval'),
      longBreakIntervalVal: document.getElementById('longBreakIntervalVal'),
      soundVolume: document.getElementById('soundVolume'),
      soundVolumeVal: document.getElementById('soundVolumeVal'),
      autoStartBreaks: document.getElementById('autoStartBreaks'),
      autoStartWork: document.getElementById('autoStartWork'),
    };

    // Initialize UI values from settings
    elements.workDuration.value = get('workDuration');
    elements.workDurationVal.textContent = get('workDuration');
    elements.shortBreakDuration.value = get('shortBreakDuration');
    elements.shortBreakDurationVal.textContent = get('shortBreakDuration');
    elements.longBreakDuration.value = get('longBreakDuration');
    elements.longBreakDurationVal.textContent = get('longBreakDuration');
    elements.longBreakInterval.value = get('longBreakInterval');
    elements.longBreakIntervalVal.textContent = get('longBreakInterval');
    elements.soundVolume.value = get('soundVolume');
    elements.soundVolumeVal.textContent = get('soundVolume') + '%';
    elements.autoStartBreaks.checked = get('autoStartBreaks');
    elements.autoStartWork.checked = get('autoStartWork');

    // Bind change events
    const rangeInputs = [
      { input: elements.workDuration, value: elements.workDurationVal, key: 'workDuration', suffix: '' },
      { input: elements.shortBreakDuration, value: elements.shortBreakDurationVal, key: 'shortBreakDuration', suffix: '' },
      { input: elements.longBreakDuration, value: elements.longBreakDurationVal, key: 'longBreakDuration', suffix: '' },
      { input: elements.longBreakInterval, value: elements.longBreakIntervalVal, key: 'longBreakInterval', suffix: '' },
      { input: elements.soundVolume, value: elements.soundVolumeVal, key: 'soundVolume', suffix: '%' },
    ];

    for (const item of rangeInputs) {
      item.input.addEventListener('input', () => {
        const val = parseInt(item.input.value, 10);
        item.value.textContent = val + item.suffix;
        set(item.key, val);

        // Apply volume immediately
        if (item.key === 'soundVolume') {
          Notifications.setVolume(val / 100);
        }
        // Emit change for other settings
        if (typeof onSettingsChange === 'function') {
          onSettingsChange(item.key, val);
        }
      });
    }

    elements.autoStartBreaks.addEventListener('change', () => {
      set('autoStartBreaks', elements.autoStartBreaks.checked);
    });

    elements.autoStartWork.addEventListener('change', () => {
      set('autoStartWork', elements.autoStartWork.checked);
    });

    // Apply initial volume
    Notifications.setVolume(get('soundVolume') / 100);
  }

  /**
   * Apply the current theme setting.
   */
  function applyTheme() {
    const theme = get('theme');
    if (theme === 'auto') {
      const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      document.documentElement.setAttribute('data-theme', prefersDark ? 'dark' : 'light');
    } else {
      document.documentElement.setAttribute('data-theme', theme);
    }
  }

  /**
   * Toggle theme between light/dark/auto.
   */
  function toggleTheme() {
    const current = get('theme');
    let next;
    if (current === 'auto') next = 'dark';
    else if (current === 'dark') next = 'light';
    else next = 'auto';
    set('theme', next);
    applyTheme();
  }

  return { load, save, get, set, bindUI, applyTheme, toggleTheme };
})();

// Callback placeholder — set by app.js
let onSettingsChange = null;

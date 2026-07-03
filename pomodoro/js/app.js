/* ============================================
   App — Main Application Logic
   ============================================ */

(function () {
  'use strict';

  // ── State ──────────────────────────────────────
  const MODES = {
    work:        { id: 'work',        icon: '🍅', label: '专注工作' },
    shortBreak:  { id: 'shortBreak',  icon: '☕', label: '短休息'   },
    longBreak:   { id: 'longBreak',   icon: '🎉', label: '长休息'   },
  };

  const timer = new PomodoroTimer();
  let currentMode = 'work';
  let completedPomodoros = 0;    // total today
  let cycleCount = 0;            // work sessions completed in current cycle

  // ── DOM References ─────────────────────────────
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  const dom = {
    modeTabs:       $$('.mode-tab'),
    timerMinutes:   $('#timerMinutes'),
    timerSeconds:   $('#timerSeconds'),
    timerDisplay:   $('.timer-display'),
    ringProgress:   $('.timer-ring-progress'),
    timerState:     $('#timerState'),
    btnStart:       $('#btnStart'),
    btnStartText:   $('#btnStartText'),
    btnReset:       $('#btnReset'),
    btnSkip:        $('#btnSkip'),
    cycleIndicator: $('#cycleIndicator'),
    todayCount:     $('#todayCount'),
    settingsModal:  $('#settingsModal'),
    btnSettingsOpen: $('#btnSettingsOpen'),
    btnSettingsClose: $('#btnSettingsClose'),
    themeToggle:    $('#themeToggle'),
  };

  const CIRCUMFERENCE = 2 * Math.PI * 90; // ~565.49

  // ── Helpers ────────────────────────────────────
  function getModeDuration() {
    switch (currentMode) {
      case 'work':       return Settings.get('workDuration');
      case 'shortBreak': return Settings.get('shortBreakDuration');
      case 'longBreak':  return Settings.get('longBreakDuration');
      default:           return 25;
    }
  }

  function formatTime(totalSeconds) {
    const m = Math.floor(totalSeconds / 60);
    const s = totalSeconds % 60;
    return {
      minutes: String(m).padStart(2, '0'),
      seconds: String(s).padStart(2, '0'),
    };
  }

  // ── UI Updates ─────────────────────────────────
  function updateTimerDisplay(remainingSeconds) {
    const { minutes, seconds } = formatTime(remainingSeconds);
    dom.timerMinutes.textContent = minutes;
    dom.timerSeconds.textContent = seconds;
  }

  function updateRing(progress) {
    // progress: 0 (full) to 1 (empty)
    const offset = CIRCUMFERENCE * progress;
    dom.ringProgress.style.strokeDasharray = CIRCUMFERENCE;
    dom.ringProgress.style.strokeDashoffset = offset;

    // Color classes
    dom.ringProgress.classList.remove('break', 'finished');
    if (currentMode !== 'work') {
      dom.ringProgress.classList.add('break');
    }
    if (progress >= 1) {
      dom.ringProgress.classList.add('finished');
    }
  }

  function updateCycleIndicator() {
    const interval = Settings.get('longBreakInterval');
    let html = '';
    for (let i = 0; i < interval; i++) {
      let cls = 'cycle-dot';
      if (i < cycleCount) cls += ' completed';
      else if (i === cycleCount) cls += ' current';
      html += `<span class="${cls}"></span>`;
    }
    dom.cycleIndicator.innerHTML = html;
    dom.cycleIndicator.setAttribute('title', `循环: ${cycleCount}/${interval}`);
  }

  function updateTodayCount() {
    dom.todayCount.innerHTML = `🍅 今日完成: <strong>${completedPomodoros}</strong> 个番茄`;
  }

  function setModeUI(mode) {
    currentMode = mode;
    dom.modeTabs.forEach(tab => {
      const isActive = tab.dataset.mode === mode;
      tab.classList.toggle('active', isActive);
      tab.setAttribute('aria-selected', isActive);
    });
    dom.ringProgress.classList.toggle('break', mode !== 'work');
    dom.timerState.textContent = MODES[mode].label;
  }

  function setRunningUI(isRunning) {
    dom.btnStart.classList.toggle('running', isRunning);
    dom.btnStartText.textContent = isRunning ? '暂停' : '开始';
    if (!isRunning) {
      dom.timerState.textContent = MODES[currentMode].label;
    }
    dom.timerDisplay.classList.remove('finished');
  }

  function setFinishedUI() {
    dom.timerDisplay.classList.add('finished');
    dom.timerState.textContent = '⏰ 时间到！';
  }

  function loadTodayCount() {
    const today = new Date().toISOString().slice(0, 10);
    const stored = localStorage.getItem('pomodoro-today');
    if (stored) {
      try {
        const data = JSON.parse(stored);
        if (data.date === today) {
          completedPomodoros = data.count;
        } else {
          completedPomodoros = 0;
        }
      } catch (e) {
        completedPomodoros = 0;
      }
    } else {
      completedPomodoros = 0;
    }
    updateTodayCount();
  }

  function saveTodayCount() {
    const today = new Date().toISOString().slice(0, 10);
    localStorage.setItem('pomodoro-today', JSON.stringify({
      date: today,
      count: completedPomodoros,
    }));
  }

  // ── Mode Transition ────────────────────────────
  function switchMode(mode) {
    setModeUI(mode);
    const duration = getModeDuration();
    timer.setDuration(duration);
    updateTimerDisplay(duration * 60);
    updateRing(0);
    updateCycleIndicator();
    dom.timerState.textContent = MODES[mode].label;
    dom.timerDisplay.classList.remove('finished');

    const shouldAutoStart = mode !== 'work'
      ? Settings.get('autoStartBreaks')
      : Settings.get('autoStartWork');

    if (shouldAutoStart) {
      // Small delay so UI feels natural
      setTimeout(() => timer.start(), 300);
    }
  }

  function handleFinish() {
    Notifications.playSound(currentMode === 'work' ? 'workEnd' : 'breakEnd');
    setFinishedUI();

    if (currentMode === 'work') {
      completedPomodoros++;
      cycleCount++;
      saveTodayCount();
      updateTodayCount();
      updateCycleIndicator();

      // Determine next mode
      const interval = Settings.get('longBreakInterval');
      if (cycleCount >= interval) {
        cycleCount = 0;
        Notifications.showNotification('🍅 番茄完成！', {
          body: `已完成 ${completedPomodoros} 个番茄，该长休息啦！`,
        });
        switchMode('longBreak');
      } else {
        Notifications.showNotification('🍅 番茄完成！', {
          body: `已完成 ${completedPomodoros} 个番茄。休息一下吧~`,
        });
        switchMode('shortBreak');
      }
    } else {
      // Break finished — go back to work
      Notifications.showNotification('⏰ 休息结束', { body: '继续加油！' });
      switchMode('work');
    }
  }

  // ── Event Handlers ─────────────────────────────
  function onStartClick() {
    // Request notification permission on first interaction
    Notifications.requestPermission();

    if (timer.getState().isRunning) {
      timer.pause();
    } else {
      if (timer.getState().remainingSeconds <= 0) {
        // Timer finished — reset first
        timer.setDuration(getModeDuration());
        updateTimerDisplay(getModeDuration() * 60);
        updateRing(0);
      }
      timer.start();
    }
  }

  function onResetClick() {
    timer.reset();
    updateTimerDisplay(getModeDuration() * 60);
    updateRing(0);
    setRunningUI(false);
    dom.timerState.textContent = MODES[currentMode].label;
    dom.timerDisplay.classList.remove('finished');
  }

  function onSkipClick() {
    timer.skip();
  }

  function onModeTabClick(e) {
    const tab = e.currentTarget;
    const mode = tab.dataset.mode;
    if (mode === currentMode && timer.getState().isRunning) return; // Don't switch if same mode and running
    timer.reset();
    setRunningUI(false);
    updateRing(0);
    switchMode(mode);
  }

  // ── Settings Modal ─────────────────────────────
  function openSettings() {
    dom.settingsModal.classList.add('open');
    dom.settingsModal.setAttribute('aria-hidden', 'false');
  }

  function closeSettings() {
    dom.settingsModal.classList.remove('open');
    dom.settingsModal.setAttribute('aria-hidden', 'true');
  }

  // Close on overlay click
  dom.settingsModal.addEventListener('click', (e) => {
    if (e.target === dom.settingsModal) closeSettings();
  });

  // ── Theme Toggle ───────────────────────────────
  dom.themeToggle.addEventListener('click', () => {
    Settings.toggleTheme();
  });

  // ── Keyboard Shortcuts ─────────────────────────
  document.addEventListener('keydown', (e) => {
    // Don't trigger shortcuts when typing in inputs
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

    switch (e.key.toLowerCase()) {
      case ' ':
        e.preventDefault();
        onStartClick();
        break;
      case 'r':
        onResetClick();
        break;
      case 's':
        onSkipClick();
        break;
    }
  });

  // ── Timer Events ───────────────────────────────
  timer.on('tick', (data) => {
    updateTimerDisplay(data.remaining);
    updateRing(data.progress);
    dom.timerState.textContent = MODES[currentMode].label;
  });

  timer.on('start', () => {
    setRunningUI(true);
    dom.timerState.textContent = MODES[currentMode].label;
    dom.timerDisplay.classList.remove('finished');
  });

  timer.on('pause', () => {
    setRunningUI(false);
  });

  timer.on('reset', (data) => {
    updateTimerDisplay(data.remaining);
    updateRing(data.progress);
  });

  timer.on('finish', () => {
    setRunningUI(false);
    handleFinish();
  });

  // ── Settings Change Handler ────────────────────
  // Called by settings.js when a setting changes
  onSettingsChange = function (key, val) {
    if (key === 'soundVolume') {
      Notifications.setVolume(val / 100);
    }
  };

  // ── Initialize ─────────────────────────────────
  function init() {
    Settings.load();
    Settings.applyTheme();
    Settings.bindUI();
    loadTodayCount();

    // Set initial timer
    const duration = getModeDuration();
    timer.setDuration(duration);
    updateTimerDisplay(duration * 60);
    updateRing(0);
    setModeUI('work');
    updateCycleIndicator();
    setRunningUI(false);

    // Bind UI events
    dom.btnStart.addEventListener('click', onStartClick);
    dom.btnReset.addEventListener('click', onResetClick);
    dom.btnSkip.addEventListener('click', onSkipClick);
    dom.btnSettingsOpen.addEventListener('click', openSettings);
    dom.btnSettingsClose.addEventListener('click', closeSettings);
    dom.modeTabs.forEach(tab => tab.addEventListener('click', onModeTabClick));

    // Close modal on Escape
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && dom.settingsModal.classList.contains('open')) {
        closeSettings();
      }
    });

    // Listen for system theme changes
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
      if (Settings.get('theme') === 'auto') {
        Settings.applyTheme();
      }
    });
  }

  init();
})();

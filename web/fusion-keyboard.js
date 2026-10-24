/* Automatic keyboard capture for Selkies fullscreen.
 * No overlay/button is added. Pointer lock is intentionally untouched. */
(() => {
  'use strict';
  if (window.__fusionKeyboardAutoLockInstalled) return;
  window.__fusionKeyboardAutoLockInstalled = true;

  const keyboard = navigator.keyboard;
  const original = Element.prototype.requestFullscreen;

  async function lockKeyboard() {
    if (!document.fullscreenElement || !keyboard || !keyboard.lock) return;
    try {
      // Empty key list means: request every key the browser/OS permits.
      await keyboard.lock();
    } catch (_) {
      // Policy/user-activation/browser support can reject the request.
      // Fullscreen itself must continue to work in that case.
    }
  }

  if (original) {
    Element.prototype.requestFullscreen = function(options) {
      // Do not pass the newer option to browsers that expose no Keyboard Lock API;
      // unsupported requestFullscreen options can reject the fullscreen request.
      const requested = (keyboard && keyboard.lock)
        ? Object.assign({}, options || {}, {keyboardLock: 'browser'})
        : options;
      const result = original.call(this, requested);
      Promise.resolve(result).then(lockKeyboard, () => {});
      return result;
    };
  }

  document.addEventListener('fullscreenchange', () => {
    if (document.fullscreenElement) lockKeyboard();
    else if (keyboard && keyboard.unlock) keyboard.unlock();
  });

  // Fallback for Chromium versions that require a fresh transient activation
  // when lock() is requested after fullscreen was already entered.
  for (const type of ['pointerup', 'keydown']) {
    document.addEventListener(type, (event) => {
      if (event.isTrusted && document.fullscreenElement) lockKeyboard();
    }, true);
  }

  window.addEventListener('focus', lockKeyboard);
  window.addEventListener('pagehide', () => {
    if (keyboard && keyboard.unlock) keyboard.unlock();
  });
})();

const fs = require('fs'), vm = require('vm'), assert = require('assert');
const code = fs.readFileSync(require('path').join(__dirname, '../web/fusion-keyboard.js'), 'utf8');
const events = {}, calls = [];
function Element() {}
Element.prototype.requestFullscreen = function(opts) {
  calls.push(['fullscreen', opts]);
  document.fullscreenElement = this;
  return Promise.resolve();
};
const document = {
  fullscreenElement: null,
  addEventListener(name, fn) { events[name] = fn; }
};
const keyboard = {
  lock() { calls.push(['lock']); return Promise.resolve(); },
  unlock() { calls.push(['unlock']); }
};
const navigator = {keyboard};
const window = {addEventListener(name, fn) { events['window:' + name] = fn; }};
vm.runInNewContext(code, {Element, document, navigator, window, Promise});
(async () => {
  const el = new Element();
  await el.requestFullscreen({navigationUI: 'hide'});
  await Promise.resolve();
  assert.equal(calls[0][1].keyboardLock, 'browser');
  assert(calls.some(c => c[0] === 'lock'));
  events.fullscreenchange();
  document.fullscreenElement = null;
  events.fullscreenchange();
  assert(calls.some(c => c[0] === 'unlock'));
  assert(!code.includes('Capture keyboard'));
  console.log('Keyboard fullscreen integration tests passed.');
})().catch(e => { console.error(e); process.exit(1); });

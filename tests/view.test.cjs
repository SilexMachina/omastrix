const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const context = vm.createContext({});
vm.runInContext(fs.readFileSync(path.join(__dirname, '../View.js'), 'utf8'), context);

const panelSource = fs.readFileSync(path.join(__dirname, '../Panel.qml'), 'utf8');

test('repeated action names identify their model or service without changing button text', () => {
  assert.equal(context.actionName('Load', 'Example model'), 'Load Example model');
  assert.equal(context.actionName('Open', 'Open WebUI'), 'Open Open WebUI');
  assert.equal(context.actionName('Refresh', ''), 'Refresh');
});

function qmlBody(marker) {
  const start = panelSource.indexOf(marker);
  assert.notEqual(start, -1, `Missing QML handler: ${marker}`);
  const opening = panelSource.indexOf('{', start);
  let depth = 1;
  let end = opening + 1;
  while (depth && end < panelSource.length) {
    if (panelSource[end] === '{') depth++;
    if (panelSource[end] === '}') depth--;
    end++;
  }
  return panelSource.slice(opening + 1, end - 1);
}

function focusFixture() {
  const window = {activeFocusItem: null};
  const catcher = {Window: {window}};
  const controls = [catcher];
  for (const [enabled, visible] of [[true, true], [false, true], [true, false], [true, true]]) {
    controls.push({enabled, visible, activeFocusOnTab: true, height: 20,
      forceActiveFocus() { window.activeFocusItem = this; },
      mapToItem() { return {y: 0}; },
      clicked() { this.clicks = (this.clicks || 0) + 1; }});
  }
  controls.forEach((item, index) => {
    item.nextItemInFocusChain = forward => controls[(index + (forward ? 1 : controls.length - 1)) % controls.length];
  });
  const scope = vm.createContext({keyCatcher: catcher, panel: {}, column: {},
    scroll: {contentY: 0, height: 100, contentHeight: 100}, Qt: {TabFocusReason: 1}, Style: {space: x => x}});
  vm.runInContext(`function moveFocus(direction) {${qmlBody('function moveFocus(direction)')}}`, scope);
  scope.root = {moveFocus: scope.moveFocus};
  return {scope, window, catcher, controls};
}

test('repeated keyboard traversal advances and skips hidden or disabled controls', () => {
  const {scope, window, controls} = focusFixture();
  scope.moveFocus(1);
  assert.equal(window.activeFocusItem, controls[1]);
  scope.moveFocus(1);
  assert.equal(window.activeFocusItem, controls[4]);
  scope.moveFocus(-1);
  assert.equal(window.activeFocusItem, controls[1]);
});

test('keyboard activation targets native focus and never clicks a disabled control', () => {
  const {scope, window, controls} = focusFixture();
  window.activeFocusItem = controls[4];
  vm.runInContext(qmlBody('onActivateRequested:'), scope);
  assert.equal(controls[4].clicks, 1);
  window.activeFocusItem = controls[2];
  vm.runInContext(qmlBody('onActivateRequested:'), scope);
  assert.equal(controls[2].clicks, undefined);
});

test('missing GTT readings stay unavailable while measured zero remains zero', () => {
  for (const value of [null, undefined, '', ' ', 'unknown', NaN, Infinity, -1, false])
    assert.equal(context.formatGttUsed(value), '—', `Unavailable: ${String(value)}`);
  assert.equal(context.formatGttUsed(0), '0.0');
  assert.equal(context.formatGttUsed(12.34), '12.3');
  assert.equal(context.formatGttUsed('12.36'), '12.4');
});

test('plugin detail distinguishes checks, commits and background updates', () => {
  assert.equal(context.pluginDetail({version:'1.0.0'}, ''), '1.0.0');
  assert.equal(context.pluginDetail({version:'1.0.0', checked_at:'now'}, ''), '1.0.0 · Up to date');
  assert.equal(context.pluginDetail({version:'1.0.0', checked_at:'old', error:'Network failed'}, ''), '1.0.0');
  assert.equal(context.pluginDetail({version:'1.0.0', latest_version:'1.1.0', update_available:true}, ''), '1.0.0 · 1.1.0 available');
  assert.equal(context.pluginDetail({version:'1.0.0', latest_version:'1.0.0', update_available:true}, ''), '1.0.0 · New revision available');
  assert.equal(context.pluginDetail({version:'1.0.0', updating:true}, ''), '1.0.0 · Updating…');
  assert.equal(context.pluginDetail({}, '0.5.0'), '0.5.0');
});

test('service detail presents update results beside its version', () => {
  assert.equal(context.serviceDetail({build: 12, latest_build: 12}, true), 'Build 12 · Up to date');
  assert.equal(context.serviceDetail({build: 12, latest_build: 13, update_available: true}, true), 'Build 12 · Build 13 available');
  assert.equal(context.serviceDetail({version: '1.2.3', latest_version: '1.2.3'}, false), '1.2.3 · Up to date');
  assert.equal(context.serviceDetail({version: '1.2.3'}, false), '1.2.3');
});

test('model loading requires a running engine and a fitting recipe', () => {
  assert.equal(context.modelAction({installed: true, fits: true}, false).enabled, false);
  assert.equal(context.modelAction({installed: true, fits: false}, true).enabled, false);
  assert.equal(context.modelAction({installed: true, fits: true}, true).verb, 'library-load');
  assert.equal(context.modelAction({installed: false, status: 'downloading'}, true).enabled, false);
});

test('explicit JSON failures and process exit codes override success', () => {
  assert.equal(context.commandResult('{"success":false,"error":"Out of memory"}', '', 0).error, 'Out of memory');
  assert.equal(context.commandResult('{"success":true}', 'process failed', 9).success, false);
  assert.equal(context.commandResult('null', '', 0).success, false);
  assert.equal(context.commandResult('[]', '', 0).success, false);
  assert.equal(context.commandResult('{"success":true}', '', 0).success, true);
});

test('a normal exit 1 preserves a validated backend confirmation request', () => {
  const result = context.commandResult('{"success":false,"needs_confirm":true,"error":"Unload the current model?"}', '', 1, 0);
  assert.equal(result.success, false);
  assert.equal(result.needs_confirm, true);
  assert.equal(result.error, 'Unload the current model?');
});

test('a crashed command cannot request confirmation or claim success', () => {
  for (const exitCode of [0, 1, 9]) {
    const result = context.commandResult('{"success":false,"needs_confirm":true}', 'crashed', exitCode, 1);
    assert.equal(result.success, false);
    assert.equal(result.needs_confirm, undefined);
    assert.equal(context.commandResult('{"success":true}', 'crashed', exitCode, 1).success, false);
  }
});

test('abnormal command exit codes cannot request confirmation', () => {
  const result = context.commandResult('{"success":false,"needs_confirm":true}', '', 9, 0);
  assert.equal(result.needs_confirm, undefined);
});

test('confirmation preserves the backend explanation', () => {
  const result = context.commandResult('{"needs_confirm":true,"error":"Unload the current model?"}', '', 0);
  assert.equal(result.needs_confirm, true);
  assert.equal(result.error, 'Unload the current model?');
});

test('loaded and inferring models offer unload', () => {
  for (const status_label of ['Loaded', 'Inferring']) {
    const result = context.modelAction({installed:true, fits:true, status_label}, true);
    assert.equal(result.verb, 'library-unload');
    assert.equal(result.text, 'Unload');
    assert.equal(result.enabled, true);
  }
});

test('service state preserves unavailable and transitional observations', () => {
  for (const state of ['unavailable', 'unrecognized']) {
    const view = context.serviceState({installed: true, state});
    assert.equal(view.text, 'Unavailable');
    assert.equal(view.primaryEnabled, false);
    assert.equal(view.stopped, false);
  }
  for (const [state, text] of [['starting', 'Starting…'], ['stopping', 'Stopping…'], ['installing', 'Installing…']]) {
    const view = context.serviceState({installed: true, state});
    assert.equal(view.text, text);
    assert.equal(view.working, true);
    assert.equal(view.primaryEnabled, false);
  }
});

test('only known applicable service states enable lifecycle actions', () => {
  for (const state of ['stopped', 'failed', 'running'])
    assert.equal(context.serviceState({installed: true, state}).primaryEnabled, true);
  assert.equal(context.serviceState({installed: false, state: 'not_installed'}).text, 'Not installed');
  assert.equal(context.serviceState({installed: false, state: 'not_installed'}).primaryEnabled, true);
  assert.equal(context.serviceState({installed: true, state: 'stopped', updating: true}).primaryEnabled, false);
});

test('command failures remain failures even without JSON or stderr', () => {
  const result = context.commandResult('', '', 1);
  assert.equal(result.success, false);
  assert.match(result.error, /failed/i);
});

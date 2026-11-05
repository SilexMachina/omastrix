#!/usr/bin/env python3
"""Isolated native Quickshell UI smoke tests; no host backend is copied/run.

Requires installed Omarchy Ui/Commons, Quickshell, QtTest. Temporary copied
Panel.qml gets aliases for private test access and substitutes ONLY the
layer-shell KeyboardPanel window with an offscreen FloatingWindow adapter:
installed Quickshell has no offscreen PanelWindow backend. Production content,
controls, and handlers remain unchanged. Compositor placement/focus ownership
are outside this harness; the copied UI is not a live desktop integration test.
Every backend response is an explicitly synthetic test fixture. No compositor
connection or desktop input is used. Artifacts persist under $TMPDIR.
"""
from pathlib import Path
import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile

REPO = Path(__file__).resolve().parents[1]
QML = r'''
import QtQuick
import QtQuick.Window
import Quickshell
import QtTest
import qs.Commons
import "plugin" as Plugin
ShellRoot {
  FloatingWindow {
    id: window
    implicitWidth: WIDTH
    implicitHeight: 900
    visible: true
    color: Color.background
    QtObject {
      id: fakeBar
      property color foreground: Color.foreground
      property color background: Color.background
      property color accent: Color.accent
      property color urgent: Color.urgent
      property color barForeground: foreground
      property string fontFamily: Style.font.family
      property int barSize: 30
      property bool vertical: false
      property bool foregroundAnimationEnabled: false
      property string position: "top"
      property var activePopout: null
      function requestPopout(owner) { activePopout = owner }
      function releasePopout(owner) { if (activePopout === owner) activePopout = null }
      function showTooltip() {}
      function hideTooltip() {}
      function run(command) { throw new Error("External action forbidden: " + command) }
    }
    Plugin.Panel { id: plugin; bar: fakeBar; manageIpc: false; width: 110; height: 30 }
    TestCase {
      id: tests
      parent: plugin.smokeKeys
      name: "OmaStrixNativeSmoke"
      when: window.visible
      function checkedVerify(value, message) {
        if (!value) { console.error("SMOKE_FAIL " + qtest_results.functionName + ": " + (message || "assertion")); fail(message || "assertion") }
      }
      function checkedCompare(actual, expected, message) {
        if (actual !== expected) { console.error("SMOKE_FAIL " + qtest_results.functionName + ": " + actual + " != " + expected); fail(message || "comparison") }
      }
      function init() { console.log("SMOKE_START " + qtest_results.functionName) }
      function cleanup() { console.log("SMOKE_END " + qtest_results.functionName + " failed=" + qtest_results.failed) }
      function nativeKey(key) {
        try { keyClick(key) } catch (error) { console.error("SMOKE_NATIVE_INPUT " + error.message); throw error }
      }
      function walk(item, predicate, result, seen) {
        if (!item || seen.indexOf(item) >= 0) return
        seen.push(item)
        if (predicate(item)) result.push(item)
        var children = item.children || []
        for (var i = 0; i < children.length; ++i) walk(children[i], predicate, result, seen)
      }
      function controls(text) {
        var result = []
        walk(plugin.smokeKeys, function(o) { return o.text === text && typeof o.clicked === "function" }, result, [])
        return result
      }
      function visibleControl(text) {
        var buttons = controls(text)
        for (var i = 0; i < buttons.length; ++i) if (buttons[i].visible) return buttons[i]
        fail("Missing visible button: " + text)
      }
      function labels(text) {
        var result = []
        walk(plugin.smokeKeys, function(o) { return o.visible && o.text === text && o.contentWidth !== undefined }, result, [])
        return result
      }
      function rect(item) {
        var p = item.mapToItem(plugin.smokeKeys, 0, 0)
        return {x: p.x, y: p.y, right: p.x + item.width, bottom: p.y + item.height}
      }
      function contained(item) {
        var r = rect(item)
        verify(r.x >= -1 && r.right <= plugin.smokeKeys.width + 1, "Outside content bounds: " + item.text)
      }
      function disjoint(a, b) {
        var x = rect(a), y = rect(b)
        verify(x.right <= y.x + 1 || y.right <= x.x + 1 || x.bottom <= y.y + 1 || y.bottom <= x.y + 1,
          "Overlapping content: " + a.text + " / " + b.text)
      }
      function reveal(item) {
        var p = item.mapToItem(plugin.smokeScroll, 0, 0)
        plugin.smokeScroll.contentY = Math.max(0, Math.min(plugin.smokeScroll.contentHeight - plugin.smokeScroll.height,
          plugin.smokeScroll.contentY + p.y - 20))
        wait(30)
      }
      function test_01b_model_layout() {
        for (var i = 0; i < plugin.models.length; ++i) {
          var row = plugin.models[i]
          var name = labels(row.name)[0]
          verify(!!name)
          contained(name)
          verify(name.width >= Math.min(name.implicitWidth, 140), "Model name remains readable: " + row.name + " width=" + name.width + " details=" + name.parent.parent.width)
          var nodes = []
          walk(name.parent.parent.parent, function(o) {
            return o.visible && typeof o.text === "string" && (typeof o.clicked === "function" || (o.contentWidth !== undefined && o.parent === name.parent.parent))
          }, nodes, [])
          // Only outer controls, not their own text children, participate.
          nodes.push(name)
          for (var j = 0; j < nodes.length; ++j) {
            contained(nodes[j])
            var nodeBounds = rect(nodes[j]), rowBounds = rect(name.parent.parent.parent)
            verify(nodeBounds.x >= rowBounds.x - 1 && nodeBounds.right <= rowBounds.right + 1,
              "Model content stays inside its row: " + nodes[j].text)
            if (nodes[j].contentWidth !== undefined && nodes[j] !== name)
              verify(nodes[j].contentWidth <= nodes[j].width + 1, "Model detail fits: " + nodes[j].text)
            if (typeof nodes[j].clicked === "function" && plugin.smokeKeys.width < 600 && Style.fontBaseSize === 18)
              verify(nodeBounds.y >= rect(name.parent.parent).bottom - 1, "Compact actions sit below model details")
            for (var k = j + 1; k < nodes.length; ++k) disjoint(nodes[j], nodes[k])
          }
        }
        reveal(labels(plugin.models[0].name)[0])
        grabImage(plugin.smokeKeys).save("SCREENSHOT.models.png")
        plugin.smokeScroll.contentY = 0
      }
      function test_01c_gtt_layout() {
        var items = [labels("GPU memory")[0], labels("Ceiling")[0]]
        var readings = []
        walk(plugin.smokeKeys, function(o) { return o.visible && o.contentWidth !== undefined && String(o.text).indexOf("GTT  ") === 0 }, readings, [])
        items = items.concat(readings, controls("64 GiB"), controls("96 GiB"), controls("110 GiB"))
        for (var i = 0; i < items.length; ++i) {
          contained(items[i])
          if (items[i].contentWidth !== undefined)
            verify(items[i].contentWidth <= items[i].width + 1, "GTT label fits: " + items[i].text)
          for (var j = i + 1; j < items.length; ++j) disjoint(items[i], items[j])
        }
      }
      function initTestCase() {
        tryVerify(function() { return plugin.hasSnapshot }, 5000)
        Color.foreground = LIGHT ? "#202020" : "#dedede"
        Color.background = LIGHT ? "#fafafa" : "#151515"
        Color.accent = LIGHT ? "#315ba0" : "#9bbcff"
        Color.urgent = LIGHT ? "#a42121" : "#ff9292"
        Color.shellValues = ({})
        Style.fontBaseSize = FONT_SIZE
        plugin.open()
        wait(250)
        verify(plugin.smokeKeys.width > 0)
        verify(plugin.smokeKeys.height > 0)
        console.log("SMOKE viewport " + plugin.smokeKeys.width + "x" + plugin.smokeKeys.height)
      }
      function test_01_render() {
        verify(plugin.halo)
        compare(plugin.models.length, 5)
        verify(plugin.smokeScroll.contentHeight > 0)
        var buttons = []
        walk(plugin.smokeKeys, function(o) { return typeof o.clicked === "function" }, buttons, [])
        verify(buttons.length >= 20)
        var checks = controls("Check updates").filter(function(button) { return button.visible })
        compare(checks.length, 2)
        compare(Math.round(checks[0].mapToItem(plugin.smokeKeys, 0, 0).x),
                Math.round(checks[1].mapToItem(plugin.smokeKeys, 0, 0).x),
                "Service action columns align even when only one update is available")
        var image = grabImage(plugin.smokeKeys)
        verify(image.width > 0 && image.height > 0)
        image.save("SCREENSHOT")
        console.log("SMOKE screenshot SCREENSHOT")
        plugin.runAction(["fixture-wait"], "engine")
        wait(60)
        verify(plugin.busy)
        var working = visibleControl("Working…")
        verify(!working.enabled)
        var point = working.mapToItem(plugin.smokeKeys, 0, 0)
        verify(point.x + working.width <= plugin.smokeKeys.width + 1, "Working text exceeds viewport")
        grabImage(plugin.smokeKeys).save("SCREENSHOT.working.png")
        tryVerify(function() { return !plugin.busy }, 5000)
        plugin.actionArgs = []
      }
      function test_02_disabled_button() {
        var buttons = []
        walk(plugin.smokeKeys, function(o) { return o.visible && typeof o.clicked === "function" }, buttons, [])
        for (var i = 0; i < buttons.length; ++i) {
          var point = buttons[i].mapToItem(plugin.smokeKeys, 0, 0)
          verify(point.x >= -1 && point.x + buttons[i].width <= plugin.smokeKeys.width + 1,
                 "Button exceeds viewport: " + buttons[i].text)
          var labels = []
          walk(buttons[i], function(o) { return o.text === buttons[i].text && o.contentWidth !== undefined }, labels, [])
          for (var j = 0; j < labels.length; ++j)
            verify(labels[j].contentWidth + 2 * buttons[i].horizontalPadding <= buttons[i].width + 1,
              "Button text exceeds its chrome: " + buttons[i].text)
        }
        var add = visibleControl("Add model")
        verify(!add.enabled)
        var before = JSON.stringify(plugin.actionArgs)
        mouseClick(add, add.width / 2, add.height / 2)
        keyClick(Qt.Key_Return)
        compare(JSON.stringify(plugin.actionArgs), before)
        compare(plugin.addLink, "")
      }
      function test_02b_contextual_accessible_names() {
        var buttons = []
        walk(plugin.smokeKeys, function(o) { return o.visible && typeof o.text === "string" && typeof o.clicked === "function" }, buttons, [])
        var checked = 0
        for (var i = 0; i < buttons.length; ++i) {
          var owner = buttons[i].parent
          while (owner && owner !== plugin.smokeKeys && owner.title === undefined && owner.modelData === undefined) owner = owner.parent
          if (!owner || owner === plugin.smokeKeys) continue
          var context = owner.title !== undefined ? owner.title : owner.modelData.name
          compare(buttons[i].Accessible.name, buttons[i].text + " " + context, "Repeated controls need a contextual accessible name")
          checked++
        }
        verify(checked >= 12)
      }
      function test_02c_service_observations() {
        var original = plugin.payload
        plugin.payload = Object.assign({}, original, {
          engine: Object.assign({}, original.engine, {state: "unavailable"}),
          webui: Object.assign({}, original.webui, {state: "stopping"})})
        wait(50)
        var labels = []
        walk(plugin.smokeKeys, function(o) { return o.text === "Unavailable" || o.text === "Stopping…" }, labels, [])
        compare(labels.length, 2, "Status failures and transitions remain visible")
        var starts = controls("Start").filter(function(button) { return button.visible })
        compare(starts.length, 2)
        verify(starts.every(function(button) { return !button.enabled }), "Unknown/transitional service states disable Start")
        verify(!visibleControl("Update").enabled, "Transitional service state disables Update")
        plugin.payload = original
      }
      function test_02d_network_access_controls() {
        var local = visibleControl("This device")
        var network = visibleControl("Local network")
        verify(local.selected && !local.enabled)
        verify(network.enabled)
        contained(local)
        contained(network)
        mouseClick(network, network.width / 2, network.height / 2)
        tryVerify(function() { return plugin.confirmation.scope === "webui" }, 5000)
        var cancel = visibleControl("Cancel")
        reveal(cancel)
        mouseClick(cancel, cancel.width / 2, cancel.height / 2)
        compare(plugin.confirmation.scope, undefined)
        var original = plugin.payload
        plugin.payload = Object.assign({}, original, {webui: Object.assign({}, original.webui, {state: "running", running: true})})
        wait(50)
        verify(!visibleControl("Local network").enabled)
        plugin.payload = original
        plugin.actionArgs = []
        plugin.smokeScroll.contentY = 0
      }
      function test_03_keyboard_traversal() {
        plugin.smokeKeys.forceActiveFocus()
        keyClick(Qt.Key_Tab)
        var first = plugin.smokeKeys.Window.window.activeFocusItem
        verify(first !== plugin.smokeKeys && first.enabled && first.activeFocusOnTab)
        keyClick(Qt.Key_Tab)
        var second = plugin.smokeKeys.Window.window.activeFocusItem
        verify(second !== first && second.enabled)
        keyClick(Qt.Key_Backtab)
        compare(plugin.smokeKeys.Window.window.activeFocusItem, first)
        for (var i = 0; i < 12; ++i) {
          var prior = plugin.smokeKeys.Window.window.activeFocusItem
          keyClick(Qt.Key_Tab)
          var next = plugin.smokeKeys.Window.window.activeFocusItem
          verify(next !== prior && next.enabled && next.activeFocusOnTab, "Repeated Tab advances to enabled controls")
        }
        plugin.smokeKeys.forceActiveFocus()
        keyClick(Qt.Key_J)
        var down = plugin.smokeKeys.Window.window.activeFocusItem
        verify(down !== plugin.smokeKeys && down.enabled)
        keyClick(Qt.Key_K)
        verify(plugin.smokeKeys.Window.window.activeFocusItem !== down)
      }
      function test_04_scoped_errors() {
        plugin.setMessage("engine", "TEST FIXTURE engine error")
        plugin.setMessage("fixture-ready", "TEST FIXTURE model error")
        compare(plugin.messageFor("engine"), "TEST FIXTURE engine error")
        compare(plugin.messageFor("fixture-ready"), "TEST FIXTURE model error")
        compare(plugin.messageFor("webui"), "")
        plugin.dismiss("engine")
        compare(plugin.messageFor("engine"), "")
        compare(plugin.messageFor("fixture-ready"), "TEST FIXTURE model error")
        plugin.dismiss("fixture-ready")
      }
      function test_04b_backend_error_recurs_after_healthy_snapshot() {
        var healthy = plugin.payload
        var scopes = ["engine", "webui", "fixture-ready"]
        var failed = Object.assign({}, healthy, {
          engine: Object.assign({}, healthy.engine, {update_error: "TEST FIXTURE recurring engine error"}),
          webui: Object.assign({}, healthy.webui, {error: "TEST FIXTURE recurring webui error"}),
          library: {rows: healthy.library.rows.map(function(row) {
            return row.id === "fixture-ready" ? Object.assign({}, row, {error: "TEST FIXTURE recurring model error"}) : row
          })}
        })
        plugin.payload = failed
        for (var i = 0; i < scopes.length; ++i) {
          verify(plugin.messageFor(scopes[i]) !== "")
          plugin.dismiss(scopes[i])
          compare(plugin.messageFor(scopes[i]), "")
        }
        plugin.payload = Object.assign({}, failed)
        for (var j = 0; j < scopes.length; ++j) compare(plugin.messageFor(scopes[j]), "")
        plugin.refresh()
        tryVerify(function() { return plugin.persistentError("engine") === "" }, 5000)
        plugin.payload = failed
        wait(40)
        for (var k = 0; k < scopes.length; ++k) {
          verify(plugin.messageFor(scopes[k]) !== "", "A new identical backend error must reappear: " + scopes[k])
          verify(labels(plugin.messageFor(scopes[k])).length > 0, "Recurring error is rendered: " + scopes[k])
        }
        plugin.payload = healthy
      }
      function test_04c_poll_preserves_model_focus() {
        var loaded = visibleControl("Unload")
        loaded.forceActiveFocus()
        var current = plugin.payload
        plugin.updateSnapshot(JSON.parse(JSON.stringify(current)))
        wait(50)
        checkedCompare(plugin.smokeKeys.Window.window.activeFocusItem.focusKey, "primary:fixture-loaded", "Polling preserves the focused model action")
        plugin.updateSnapshot(Object.assign({}, current, {library: Object.assign({}, current.library, {
          rows: current.library.rows.map(function(row) { return Object.assign({}, row, {ram: "8 GiB"}) })
        })}))
        wait(50)
        checkedCompare(plugin.smokeKeys.Window.window.activeFocusItem.focusKey, "primary:fixture-loaded", "Updated readings preserve the focused model action")
        plugin.payload = current
      }
      function test_05_inline_cancel() {
        plugin.requestGtt("96")
        wait(80)
        compare(plugin.confirmation.scope, "gtt")
        verify(/administrator|privileg/i.test(plugin.confirmation.text), "GTT confirmation explains authorization")
        verify(/boot configuration files/i.test(plugin.confirmation.text), "GTT confirmation explains which privileged files change")
        verify(/reboot separately to apply/i.test(plugin.confirmation.text), "Reboot remains a separate decision")
        verify(visibleControl("Confirm").enabled)
        var cancel = visibleControl("Cancel")
        reveal(cancel)
        mouseClick(cancel, cancel.width / 2, cancel.height / 2)
        wait(80)
        checkedCompare(plugin.confirmation.scope, undefined)
        compare(plugin.actionArgs.length, 0)
        plugin.smokeScroll.contentY = 0
      }
      function test_06_fixture_confirmation() {
        plugin.runAction(["library-delete", "fixture-ready"], "fixture-ready")
        tryVerify(function() { return plugin.confirmation.scope === "fixture-ready" }, 5000)
        compare(plugin.confirmation.scope, "fixture-ready")
        wait(80)
        var confirm = visibleControl("Confirm")
        reveal(confirm)
        mouseClick(confirm, confirm.width / 2, confirm.height / 2)
        tryVerify(function() { return plugin.messageFor("fixture-ready") !== "" }, 5000)
        compare(plugin.confirmation.scope, undefined)
        compare(plugin.messageFor("fixture-ready"), "TEST FIXTURE simulated delete failure; no files touched")
        compare(plugin.messageFor("engine"), "")
        compare(plugin.messageFor("webui"), "")
        plugin.dismiss("fixture-ready")
      }
      function test_07_editor_input() {
        plugin.smokeLink.forceActiveFocus()
        keyClick(Qt.Key_J)
        keyClick(Qt.Key_K)
        keyClick(Qt.Key_Space)
        compare(plugin.addLink, "jk ", "Navigation keys must remain editable text")
        keyClick(Qt.Key_Escape)
        verify(!plugin.smokeLink.activeFocus)
        verify(plugin.opened, "Escape leaves the editor without closing the panel")
        plugin.addLink = "https://fixture.invalid/model.gguf"
        wait(30)
        plugin.smokeLink.forceActiveFocus()
        keyClick(Qt.Key_Return)
        tryVerify(function() { return !plugin.busy && plugin.addLink === "" }, 5000)
        compare(plugin.messageFor("add"), "")
      }
      function test_08_scroll_and_persistent_feedback() {
        var original = plugin.payload
        var rows = original.library.rows.slice()
        for (var i = 0; i < 15; ++i)
          rows.push(Object.assign({}, rows[0], {id: "fixture-extra-" + i,
            name: "TEST FIXTURE long model name repeated for truncation and scrolling " + i}))
        plugin.payload = Object.assign({}, original, {library: {rows: rows}})
        plugin.setMessage("engine", "TEST FIXTURE engine failure. Retry the affected action or dismiss this message. "
          + "A longer explanation must wrap within the service row without hiding its controls.")
        wait(100)
        verify(plugin.smokeScroll.contentHeight > plugin.smokeScroll.height)
        var deletes = controls("Delete").filter(function(button) { return button.visible })
        deletes[deletes.length - 2].forceActiveFocus()
        plugin.moveFocus(1)
        wait(30)
        verify(plugin.smokeScroll.contentY > 0, "Keyboard navigation scrolls to lower rows")
        var focused = plugin.smokeKeys.Window.window.activeFocusItem
        var point = focused.mapToItem(plugin.smokeScroll, 0, 0)
        verify(point.y >= 0 && point.y + focused.height <= plugin.smokeScroll.height + 1,
          "Focused action remains in the viewport")
        plugin.smokeScroll.contentY = 0
        grabImage(plugin.smokeKeys).save("SCREENSHOT.feedback.png")
        plugin.refresh()
        wait(200)
        verify(plugin.messageFor("engine").indexOf("TEST FIXTURE engine failure") === 0,
          "Status polling must not erase action failures")
        plugin.dismiss("engine")
        plugin.payload = original
      }
      function test_09_escape_cancels_confirmation() {
        plugin.requestGtt("96")
        wait(30)
        plugin.smokeKeys.forceActiveFocus()
        keyClick(Qt.Key_Escape)
        compare(plugin.confirmation.scope, undefined)
        verify(plugin.opened, "Escape cancels the confirmation before closing the panel")
      }
      function cleanupTestCase() { console.log("SMOKE_COMPLETE"); Qt.quit() }
    }
  }
}
'''


def fixture() -> dict:
    rows = []
    for ident, label, installed, fits, status in [
        ("ready", "Not Loaded", True, True, "ready"),
        ("loaded", "Loaded", True, True, "ready"),
        ("oversize", "Not Loaded", True, False, "ready"),
        ("remote", "Not Installed", False, True, "available"),
        ("downloading", "Not Installed", False, True, "downloading"),
    ]:
        rows.append(dict(id="fixture-" + ident, name="TEST FIXTURE " + ident,
                         quant="Q4_K_M", params="8B", size="4.5 GiB", ram="7 GiB",
                         status_label=label, installed=installed, fits=fits, status=status,
                         deletable=installed, progress=35, notes="TEST FIXTURE memory budget" if not fits else ""))
    return dict(test_fixture="SYNTHETIC UI SMOKE DATA; NOT HOST STATUS", strix_halo=True,
                app_version="TEST FIXTURE", pill="GTT TEST", gtt_set="64", gtt_choices=["64", "96"],
                gtt_used_gib=12, gtt_total_gib=64, engine=dict(installed=True, state="running", build="TEST"),
                webui=dict(installed=True, running=False, state="stopped", version="TEST", access="local", bind_host="127.0.0.1", update_available=True, latest_version="TEST-NEXT"), library=dict(rows=rows))


# Offscreen Quickshell has no layer-shell PanelWindow backend. This adapter
# replaces ONLY the platform window, keeping all production content/handlers and
# installed Ui controls. It cannot test compositor placement/focus ownership.
WINDOW_ADAPTER = '''import QtQuick
import Quickshell
import qs.Commons
import qs.Commons as Commons
import qs.Ui
FloatingWindow {
  id: root
  required property Item anchorItem
  required property QtObject bar
  property var owner
  property bool open: false
  property Item focusTarget
  property int contentWidth: 100
  property int contentHeight: 100
  property int padding: Style.spacing.popupPadding
  property var borderSpec: Border.surfaceSpec("popups", "border", Commons.Color.popups.border, Math.max(1, Style.space(2)))
  readonly property real verticalContentInset: padding * 2 + Border.top(borderSpec) + Border.bottom(borderSpec)
  default property alias contentItem: contentHolder.children
  visible: open
  implicitWidth: contentWidth
  implicitHeight: contentHeight
  color: bar.background
  function fittedContentWidth(value) { return Math.round(Math.min(value, Math.max(120, Number(Quickshell.env("SMOKE_WIDTH")) - Style.gapsOut * 2))) }
  function fittedContentHeight(value, cap) { return Math.round(Math.min(value + verticalContentInset, cap, 900 - bar.barSize - Style.gapsOut * 2)) }
  onOpenChanged: if (open && focusTarget) Qt.callLater(function() { focusTarget.forceActiveFocus() })
  BorderSurface {
    id: card
    width: root.contentWidth
    height: root.contentHeight
    color: Commons.Color.popups.background
    padding: root.padding
    borderSpec: root.borderSpec
    radius: Style.cornerRadius
    Item {
      id: contentHolder
      anchors.fill: parent
      anchors.topMargin: card.contentTopInset
      anchors.rightMargin: card.contentRightInset
      anchors.bottomMargin: card.contentBottomInset
      anchors.leftMargin: card.contentLeftInset
    }
  }
}
'''

BACKEND = '''#!/usr/bin/python3
# SYNTHETIC TEST FIXTURE. No production backend/imports/external operations.
from pathlib import Path
import json, sys
base = Path(__file__).resolve().parent.parent
args = sys.argv[1:]
with (base / "backend-calls.jsonl").open("a") as log:
    log.write(json.dumps(args) + "\\n")
if args == ["snapshot"]:
    print((base / "snapshot.json").read_text())
elif args == ["webui-install"]:
    print(json.dumps(dict(success=True)))
elif args == ["library-download", "fixture-remote"]:
    print(json.dumps(dict(success=True)))
elif args == ["webui-access", "network"]:
    print(json.dumps(dict(success=False, needs_confirm=True, error="TEST FIXTURE allow network access?")))
    sys.exit(1)
elif args == ["fixture-wait"]:
    import time
    time.sleep(0.5)
    print(json.dumps(dict(success=True)))
elif args == ["library-add", "https://fixture.invalid/model.gguf"]:
    print(json.dumps(dict(success=True)))
elif args == ["library-delete", "fixture-ready"]:
    print(json.dumps(dict(success=False, needs_confirm=True, error="TEST FIXTURE confirmation; no deletion")))
    sys.exit(1)
elif args == ["library-delete", "fixture-ready", "--confirm"]:
    print(json.dumps(dict(success=False, error="TEST FIXTURE simulated delete failure; no files touched")))
    sys.exit(1)
else:
    print(json.dumps(dict(success=False, error="TEST HARNESS DENIED unexpected command")))
    sys.exit(97)
'''


def run_case(base, name, light, width, quickshell, installed, font_size=12):
    case = base / name
    case.mkdir()
    for directory in installed.iterdir():
        if directory.is_dir():
            (case / directory.name).symlink_to(directory, target_is_directory=True)
    plugin = case / "plugin"
    (plugin / "bin").mkdir(parents=True)
    for filename in ("Panel.qml", "ActionButton.qml", "View.js"):
        shutil.copy2(REPO / filename, plugin / filename)
    panel = (plugin / "Panel.qml").read_text()
    panel = panel.replace('  id: root\n', '  id: root\n  property alias smokePanel: panel\n  property alias smokeKeys: keyCatcher\n  property alias smokeScroll: scroll\n  property alias smokeLink: linkField\n', 1)
    panel = panel.replace('  KeyboardPanel {', '  SmokeKeyboardPanel {', 1)
    (plugin / "Panel.qml").write_text(panel)
    (plugin / "SmokeKeyboardPanel.qml").write_text(WINDOW_ADAPTER)
    snapshot = fixture()
    unsupported = name.startswith("unsupported")
    if unsupported:
        snapshot.update(strix_halo=False, gtt_choices=[], gtt_total_gib=None)
        snapshot["engine"].update(state="stopped")
    (plugin / "snapshot.json").write_text(json.dumps(snapshot))
    script = plugin / "bin/omastrix"
    script.write_text(BACKEND)
    script.chmod(0o755)
    screenshot = case / "render.png"
    qml = QML.replace("WIDTH", str(width)).replace("LIGHT", str(light).lower()).replace("SCREENSHOT", str(screenshot)).replace("FONT_SIZE", str(font_size))
    if unsupported:
        # A dedicated hardware-policy scenario; ordinary inference fixtures do
        # not describe unsupported machines and are not counted as coverage.
        qml = re.sub(r"function (test_\w+)\(", r"function helper_\1(", qml)
        qml = qml.replace('      function cleanupTestCase()', r'''      function test_unsupported_hardware_policy() {
        verify(!plugin.halo, "unsupported fixture")
        var warning = labels("Hardware Unsupported - strix-llama.cpp will not function")[0]
        verify(!!warning, "header warning visible")
        compare(warning.color, plugin.urgent)
        contained(warning)
        verify(warning.width >= Math.min(plugin.smokeKeys.width, 300), "hardware warning remains readable")
        verify(warning.contentWidth <= warning.width + 1, "warning fits header")
        var starts = controls("Start").filter(function(b) { return b.visible })
        compare(starts.length, 2)
        var engineStart = starts.filter(function(b) { return b.actionContext === "strix-llama.cpp" })[0]
        verify(!engineStart.enabled, "engine start disabled")
        compare(engineStart.foreground, plugin.urgent)
        verify(starts.filter(function(b) { return b.actionContext === "Open WebUI" })[0].enabled, "WebUI start enabled")
        for (var size of ["64 GiB", "96 GiB", "110 GiB"]) verify(!visibleControl(size).enabled, "GTT disabled: " + size)
        var installs = controls("Install").filter(function(b) { return b.visible && b.enabled })
        verify(installs.length > 0, "Model downloads remain enabled")
        var remote = installs.filter(function(b) { return b.actionContext === "TEST FIXTURE remote" })[0]
        reveal(remote)
        mouseClick(remote, remote.width / 2, remote.height / 2)
        tryVerify(function() { return !plugin.busy && plugin.actionArgs[0] === "library-download" }, 5000)
        compare(plugin.messageFor("fixture-remote"), "")
        wait(150) // Allow the action-triggered snapshot to finish.
        var original = plugin.payload
        plugin.payload = Object.assign({}, original, {engine: {installed: false, state: "not_installed"}})
        wait(50)
        verify(controls("Install").some(function(b) { return b.actionContext === "strix-llama.cpp" && b.enabled }), "engine install enabled")
        plugin.payload = Object.assign({}, original, {webui: {installed: false, state: "not_installed"}})
        wait(50)
        var webuiInstall = controls("Install").filter(function(b) { return b.actionContext === "Open WebUI" })[0]
        verify(!!webuiInstall && webuiInstall.enabled, "Fresh WebUI Install is enabled on unsupported hardware")
        reveal(webuiInstall)
        mouseClick(webuiInstall, webuiInstall.width / 2, webuiInstall.height / 2)
        tryVerify(function() { return !plugin.busy && plugin.actionArgs[0] === "webui-install" }, 5000)
        compare(plugin.messageFor("webui"), "")
        wait(150)
        plugin.payload = original
        plugin.smokeScroll.contentY = 0
        wait(50)
        grabImage(plugin.smokeKeys).save("SCREENSHOT")
      }
      function cleanupTestCase()'''.replace("SCREENSHOT", str(screenshot)))
    qml = re.sub(r"\bverify\(", "checkedVerify(", qml)
    qml = re.sub(r"\bcompare\(", "checkedCompare(", qml)
    qml = qml.replace("import qs.Commons\n", "import qs.Commons\nimport qs.Commons as Commons\n").replace("Color.", "Commons.Color.")
    (case / "shell.qml").write_text(qml)
    home = case / "home"
    home.mkdir()
    runtime = case / "runtime"
    runtime.mkdir(mode=0o700)
    runtime_fd = os.open(runtime, os.O_RDONLY | os.O_DIRECTORY)
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software", HOME=str(home),
               XDG_CONFIG_HOME=str(home / ".config"), XDG_CACHE_HOME=str(home / ".cache"),
               XDG_STATE_HOME=str(home / ".local/state"), XDG_RUNTIME_DIR=f"/proc/self/fd/{runtime_fd}",
               SMOKE_WIDTH=str(width), NO_COLOR="1")
    for key in ("WAYLAND_DISPLAY", "DISPLAY", "HYPRLAND_INSTANCE_SIGNATURE", "DBUS_SESSION_BUS_ADDRESS"):
        env.pop(key, None)
    try:
        proc = subprocess.run([quickshell, "--no-color", "--path", str(case)], env=env,
                              pass_fds=(runtime_fd,), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30)
        output = proc.stdout
        code = proc.returncode
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or b"").decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        output += "\nHARNESS TIMEOUT (30 seconds)\n"
        code = 124
    finally:
        os.close(runtime_fd)
    (case / "quickshell.log").write_text(output)
    print(f"=== {name} exit={code} ===\n{output}")
    callfile = plugin / "backend-calls.jsonl"
    calls = [json.loads(line) for line in callfile.read_text().splitlines()] if callfile.exists() else []
    allowed = [["webui-install"], ["library-download", "fixture-remote"], ["webui-access", "network"], ["snapshot"], ["fixture-wait"], ["library-add", "https://fixture.invalid/model.gguf"], ["library-delete", "fixture-ready"], ["library-delete", "fixture-ready", "--confirm"]]
    unexpected = [call for call in calls if call not in allowed]
    platform_warnings = [line for line in output.splitlines() if line.strip() == "WARN: This plugin does not support setting window masks"]
    bad_log = [line for line in output.splitlines() if re.search(r"\b(?:WARN|ERROR|FAIL!)\b", line) and line not in platform_warnings]
    outcomes = re.findall(r"SMOKE_END (test_\w+) failed=(true|false)", output)
    ok = (code == 0 and "SMOKE_COMPLETE" in output and len(outcomes) == (1 if unsupported else 16)
          and all(failed == "false" for _, failed in outcomes)
          and not unexpected and not bad_log and screenshot.exists())
    return dict(name=name, passed=ok, exit_code=code, warnings_errors=sorted(set(bad_log)),
                platform_warnings=sorted(set(platform_warnings)), tests=dict(outcomes), backend_calls=calls,
                screenshot=str(screenshot) if screenshot.exists() else None, log=str(case / "quickshell.log"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=["dark", "light", "narrow", "compact", "large-font", "compact-large-font", "unsupported", "unsupported-compact", "all"], default="all")
    args = parser.parse_args()
    quickshell = shutil.which("quickshell")
    installed = Path("/usr/share/omarchy/shell")
    if not quickshell or not (installed / "Ui").is_dir():
        parser.error("installed Quickshell and /usr/share/omarchy/shell/Ui are required")
    base = Path(tempfile.mkdtemp(prefix="omastrix-qml-smoke-", dir=os.environ.get("TMPDIR")))
    results = []
    for name, light, width, font_size in [("dark", False, 1280, 12), ("light", True, 1280, 12),
                                         ("narrow", False, 760, 12), ("compact", False, 600, 12),
                                         ("large-font", False, 960, 18), ("compact-large-font", False, 600, 18), ("unsupported", False, 1280, 12),
                                         ("unsupported-compact", False, 600, 18)]:
        if args.case in ("all", name):
            results.append(run_case(base, name, light, width, quickshell, installed, font_size))
    summary = dict(test_fixture=True, artifacts=str(base), results=results)
    (base / "results.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return 0 if all(result["passed"] for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

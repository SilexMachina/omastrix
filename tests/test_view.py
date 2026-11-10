"""View contracts plus executable tests of the shared presentation rules."""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ViewTests(unittest.TestCase):
    def test_unsupported_hardware_keeps_controls_visible_and_blocks_engine_start(self):
        source = (ROOT / 'Panel.qml').read_text()
        self.assertIn('Hardware Unsupported - strix-llama.cpp will not function', source)
        self.assertNotIn('if (busy || !halo) return', source)
        self.assertNotIn('visible: root.halo', source)
        self.assertIn('unsupportedStart', source)
        self.assertIn('!service.unsupportedStart', source)
        self.assertIn('root.halo && root.engine.state === "running"', source)

    def test_plugin_updates_have_scoped_native_controls(self):
        source = (ROOT / 'Panel.qml').read_text()
        self.assertIn('["plugin-check"]', source)
        self.assertIn('["plugin-update"]', source)
        self.assertIn('scope: "plugin"', source)
        self.assertIn('View.pluginDetail', source)

    def test_webui_has_explicit_local_and_network_access_controls(self):
        source = (ROOT / 'Panel.qml').read_text()
        self.assertIn('text: "This device"', source)
        self.assertIn('text: "Local network"', source)
        self.assertIn('["webui-access", "network"]', source)
        self.assertIn('["webui-access", "local"]', source)

    def test_refresh_stays_enabled_during_background_polling(self):
        source = (ROOT / 'Panel.qml').read_text()
        refresh = next(line for line in source.splitlines() if 'text: "Refresh"' in line)
        self.assertNotIn('enabled:', refresh)
        self.assertIn('if (snapshotProc.running) return', source)

    def test_process_exit_status_reaches_result_validation(self):
        source = (ROOT / 'Panel.qml').read_text()
        self.assertIn('function finishAction(exitCode, exitStatus)', source)
        self.assertIn('View.commandResult(actionOut.text, actionErr.text, exitCode, exitStatus)', source)
        self.assertIn('onExited: function(code, exitStatus) { root.finishAction(code, exitStatus) }', source)
        self.assertIn('View.commandResult(gttOut.text, gttErr.text, code, exitStatus)', source)

    def test_focus_comes_from_the_native_quick_window(self):
        source = (ROOT / 'Panel.qml').read_text()
        self.assertIn('import QtQuick.Window', source)
        self.assertNotIn('panel.activeFocusItem', source)
        self.assertGreaterEqual(source.count('keyCatcher.Window.window'), 2)
        self.assertIn('blocked: linkField.activeFocus', source)
        self.assertIn('target.enabled', source)

    def test_theme_colors_use_the_commons_namespace(self):
        source = (ROOT / 'Panel.qml').read_text()
        self.assertIn('import qs.Commons as Commons', source)
        self.assertNotRegex(source, r'(?<!Commons\.)\bColor\.')

    def test_service_controls_wrap_below_the_header_on_narrow_panels(self):
        source = (ROOT / 'Panel.qml').read_text().split('component ServiceRow:', 1)[1]
        self.assertIn('GridLayout {', source)
        self.assertIn('columns: service.width < Style.space(800) ? 1 : 2', source)
        self.assertIn('Flow {', source)
        self.assertIn('wrapMode: Text.Wrap', source)
        self.assertIn('Layout.minimumWidth: serviceLayout.columns === 1 ? 0 : naturalWidth', source)

    def test_model_actions_reserve_space_for_pending_labels(self):
        source = (ROOT / 'Panel.qml').read_text()
        self.assertIn('modelActionFont.advanceWidth', source)
        self.assertIn('"Installing…", "Working…"', source)
        self.assertIn('width: root.modelPrimaryWidth', source)
        self.assertIn('width: root.modelDeleteWidth', source)
        self.assertIn('root.modelPrimaryWidth + root.modelDeleteWidth + Style.space(8)', source)

    def test_native_adapter_preserves_popup_content_insets(self):
        source = (ROOT / 'tests/qml_smoke.py').read_text()
        adapter = source.split("WINDOW_ADAPTER = '''", 1)[1].split("'''", 1)[0]
        self.assertIn('padding: Style.spacing.popupPadding', adapter)
        self.assertIn('Border.surfaceSpec("popups", "border"', adapter)
        for edge in ('top', 'right', 'bottom', 'left'):
            self.assertIn(f'anchors.{edge}Margin: card.content{edge.title()}Inset', adapter)
        self.assertIn('value + verticalContentInset', adapter)
        self.assertIn('("compact-large-font", False, 600, 18)', source)

    def test_presentation_rules(self):
        result = subprocess.run(['node', '--test', str(ROOT / 'tests/view.test.cjs')], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_panel_uses_contextual_feedback(self):
        source = (ROOT / 'Panel.qml').read_text()
        self.assertIn('function messageFor(scope)', source)
        self.assertNotIn('property string updateNote:', source)
        self.assertNotIn('function later(', source)

    def test_actions_are_visible_keyboard_accessible_buttons(self):
        source = (ROOT / 'ActionButton.qml').read_text()
        self.assertIn('bordered: true', source)
        self.assertIn('focusable: true', source)
        self.assertIn('Accessible.Button', source)

    def test_panel_scrolls_instead_of_clipping_models(self):
        source = (ROOT / 'Panel.qml').read_text()
        self.assertIn('ScrollBar.vertical', source)
        self.assertIn('Flickable', source)
        self.assertIn('onMoveRequested:', source)

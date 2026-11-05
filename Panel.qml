import QtQuick
import QtQuick.Layouts
import QtQuick.Window
import QtQuick.Controls as Controls
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Commons as Commons
import qs.Ui
import "View.js" as View

Panel {
  id: root
  moduleName: "silexmachina.omastrix"
  ipcTarget: "silexmachina.omastrix"

  property var payload: ({})
  property var messages: ({})
  property var dismissed: ({})
  property var confirmation: ({})
  property string actionScope: ""
  property var actionArgs: []
  property string addLink: ""
  property string statusError: ""
  readonly property bool busy: actionProc.running || gttProc.running
  readonly property bool halo: payload.strix_halo === true
  readonly property bool hasSnapshot: payload.strix_halo !== undefined
  readonly property var engine: payload.engine || ({})
  readonly property var webui: payload.webui || ({})
  readonly property var pluginInfo: payload.plugin || ({})
  readonly property var models: payload.library ? (payload.library.rows || []) : []
  readonly property color foreground: bar ? bar.foreground : Commons.Color.foreground
  readonly property color urgent: bar ? bar.urgent : Commons.Color.urgent
  readonly property color paneBorder: Qt.alpha(foreground, 0.22)
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family
  readonly property int rowGap: Style.space(14)
  readonly property int statusWidth: Style.space(125)
  readonly property int numberWidth: Style.space(80)
  // Reserve the widest pending label plus the kit's actual themed borders.
  readonly property var actionBorders: ["normal", "hover-cursor", "selected", "focus"].map(function(state) { return Border.controlWidths(state) })
  readonly property real modelButtonChrome: Style.space(24)
    + Math.max.apply(null, actionBorders.map(function(border) { return border.left }))
    + Math.max.apply(null, actionBorders.map(function(border) { return border.right }))
  readonly property int modelPrimaryWidth: Math.ceil(modelButtonChrome + Math.max.apply(null,
    ["Install", "Load", "Unload", "Installing…", "Working…"].map(function(text) { return root.actionTextWidth(text) })))
  readonly property int modelDeleteWidth: Math.ceil(modelButtonChrome + root.actionTextWidth("Delete"))
  readonly property int servicePrimaryWidth: Math.ceil(modelButtonChrome + Math.max.apply(null,
    ["Install", "Start", "Stop", "Working…"].map(function(text) { return root.actionTextWidth(text) })))
  readonly property int serviceCheckWidth: Math.ceil(modelButtonChrome + Math.max(
    root.actionTextWidth("Check updates"), root.actionTextWidth("Checking…")))
  readonly property int serviceUpdateWidth: Math.ceil(modelButtonChrome + Math.max(root.actionTextWidth("Update"), root.actionTextWidth("Updating…")))
  readonly property int actionsWidth: root.modelPrimaryWidth + root.modelDeleteWidth + Style.space(8)

  FontMetrics { id: modelActionFont; font.family: Style.font.family; font.pixelSize: Style.font.body }

  function actionTextWidth(text) {
    // advanceWidth() has no change signal. Observe a metric so a live font
    // change invalidates the shared column widths after Qt updates the font.
    var metric = modelActionFont.averageCharacterWidth
    return modelActionFont.advanceWidth(text)
  }

  function scriptPath() {
    return decodeURIComponent(Qt.resolvedUrl("bin/omastrix").toString().replace(/^file:\/\//, ""))
  }

  function refresh() {
    if (snapshotProc.running) return
    snapshotProc.command = [scriptPath(), "snapshot"]
    snapshotProc.running = true
  }

  function setMessage(scope, text) {
    var next = Object.assign({}, messages)
    next[scope] = text
    messages = next
  }

  function persistentError(scope) {
    if (scope === "engine") return engine.update_error || ""
    if (scope === "webui") return webui.error || ""
    if (scope === "plugin") return pluginInfo.error || ""
    for (var i = 0; i < models.length; ++i)
      if (models[i].id === scope) return models[i].error || ""
    return ""
  }

  function messageFor(scope) {
    var error = persistentError(scope)
    return messages[scope] || (dismissed[scope] !== error ? error : "") || ""
  }

  function dismiss(scope) {
    setMessage(scope, "")
    var next = Object.assign({}, dismissed)
    next[scope] = persistentError(scope)
    dismissed = next
  }

  function runAction(args, scope) {
    if (busy || !hasSnapshot) return
    confirmation = ({})
    actionArgs = args
    actionScope = scope
    dismiss(scope)
    actionProc.command = [scriptPath()].concat(args)
    actionProc.running = true
  }

  function finishAction(exitCode, exitStatus) {
    var info = View.commandResult(actionOut.text, actionErr.text, exitCode, exitStatus)
    if (info.needs_confirm) {
      confirmation = {scope: actionScope, args: actionArgs, text: info.error || "Confirm this action?"}
    } else if (!info.success) {
      setMessage(actionScope, info.error)
    } else if (actionArgs[0] === "library-add") {
      addLink = ""
    }
    refresh()
  }

  function addModel() {
    if (addLink.trim() === "") return
    runAction(["library-add", addLink.trim()], "add")
  }

  function requestGtt(value) {
    if (busy || !halo || String(value) === String(payload.gtt_set)) return
    confirmation = {scope: "gtt", value: String(value), text: "Set the GTT ceiling to " + value + " GiB? Administrator authorization is required to update boot configuration files. Reboot separately to apply."}
  }

  function confirmAction() {
    var request = confirmation
    confirmation = ({})
    if (request.scope === "gtt") {
      dismiss("gtt")
      gttProc.command = ["pkexec", scriptPath(), "set-gtt", request.value]
      gttProc.running = true
    } else if (request.args) {
      runAction(request.args.concat(["--confirm"]), request.scope)
    }
  }

  // Tab and j/k walk the same real controls. Keep keyboard focus in view.
  function moveFocus(direction) {
    var window = keyCatcher.Window.window
    var item = (window && window.activeFocusItem) || keyCatcher
    for (var i = 0; i < 200; ++i) {
      item = item.nextItemInFocusChain(direction > 0)
      if (!item || item === keyCatcher) continue
      if (item.visible && item.enabled && item.activeFocusOnTab) {
        item.forceActiveFocus(Qt.TabFocusReason)
        var point = item.mapToItem(column, 0, 0)
        if (point.y < scroll.contentY) scroll.contentY = Math.max(0, point.y - Style.space(8))
        else if (point.y + item.height > scroll.contentY + scroll.height)
          scroll.contentY = Math.min(scroll.contentHeight - scroll.height, point.y + item.height - scroll.height + Style.space(8))
        return
      }
    }
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight
  Component.onCompleted: refresh()
  function updateSnapshot(next) {
    var window = keyCatcher.Window.window
    var focused = window && window.activeFocusItem
    var key = focused && focused.focusKey ? focused.focusKey : ""
    payload = next
    if (!key) return
    Qt.callLater(function() {
      function restore(item) {
        if (item.focusKey === key && item.visible && item.enabled) {
          item.forceActiveFocus(Qt.OtherFocusReason)
          return true
        }
        var children = item.children || []
        for (var i = 0; i < children.length; ++i) if (restore(children[i])) return true
        return false
      }
      if (root.opened) restore(column)
    })
  }

  onPayloadChanged: {
    // A dismissal belongs only to the current uninterrupted error occurrence.
    var next = Object.assign({}, dismissed)
    Object.keys(next).forEach(function(scope) {
      if (next[scope] !== root.persistentError(scope)) delete next[scope]
    })
    dismissed = next
  }
  onOpenedChanged: if (!opened) confirmation = ({})

  Timer {
    interval: root.opened || (root.payload.library && root.payload.library.generating) ? 2000
      : Math.max(2, Number(root.setting("refreshIntervalSec", 5))) * 1000
    running: true
    repeat: true
    onTriggered: root.refresh()
  }

  Process {
    id: snapshotProc
    stdout: StdioCollector { id: snapshotOut; waitForEnd: true }
    stderr: StdioCollector { id: snapshotErr; waitForEnd: true }
    onExited: function(code) {
      try {
        if (code !== 0) throw new Error("snapshot failed")
        var next = JSON.parse(snapshotOut.text)
        if (typeof next.strix_halo !== "boolean") throw new Error("invalid snapshot")
        root.updateSnapshot(next)
        root.statusError = ""
      } catch (_) {
        root.statusError = "Could not refresh status. " + (snapshotErr.text.trim() || "Try Refresh.")
      }
    }
  }

  Process {
    id: actionProc
    stdout: StdioCollector { id: actionOut; waitForEnd: true }
    stderr: StdioCollector { id: actionErr; waitForEnd: true }
    onExited: function(code, exitStatus) { root.finishAction(code, exitStatus) }
  }

  Process {
    id: gttProc
    stdout: StdioCollector { id: gttOut; waitForEnd: true }
    stderr: StdioCollector { id: gttErr; waitForEnd: true }
    onExited: function(code, exitStatus) {
      var info = View.commandResult(gttOut.text, gttErr.text, code, exitStatus)
      if (!info.success) root.setMessage("gtt", info.error)
      root.refresh()
    }
  }

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: root.payload.pill || "GTT ?"
    active: (root.hasSnapshot && (!root.halo || root.payload.gtt_default))
      || root.engine.state === "failed" || (root.halo && root.engine.state !== "running") || root.statusError !== ""
    fontSize: Style.font.title
    horizontalMargin: 8.75
    tooltipText: "OmaStrix" + (root.payload.gtt_pending ? " · Reboot to apply GTT change" : "")
    onPressed: function(code) {
      if (code === Qt.MiddleButton) root.refresh()
      else root.toggle()
    }
  }

  KeyboardPanel {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(1180))
    contentHeight: panel.fittedContentHeight(column.implicitHeight, Style.space(1000))

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      blocked: linkField.activeFocus
      onCloseRequested: {
        if (root.confirmation.scope) root.confirmation = ({})
        else root.close()
      }
      onMoveRequested: function(dx, dy) { root.moveFocus(dx || dy) }
      onTabRequested: function(direction) { root.moveFocus(direction) }
      onActivateRequested: {
        var window = keyCatcher.Window.window
        var target = window && window.activeFocusItem
        if (target && target !== keyCatcher && target.visible && target.enabled && typeof target.clicked === "function") target.clicked()
        else root.moveFocus(1)
      }


      Flickable {
        id: scroll
        anchors.fill: parent
        contentWidth: width
        contentHeight: column.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        Controls.ScrollBar.vertical: Controls.ScrollBar { policy: Controls.ScrollBar.AsNeeded }

        Column {
          id: column
          width: scroll.width - (scroll.contentHeight > scroll.height ? Style.space(14) : 0)
          spacing: Style.space(18)

          GridLayout {
            id: headerLayout
            width: parent.width
            readonly property bool compact: width < Style.space(800)
            columns: compact ? 3 : 4
            columnSpacing: Style.space(8)
            rowSpacing: Style.space(10)
            Column {
              Layout.row: 0
              Layout.column: 0
              Layout.fillWidth: true
              Layout.minimumWidth: 0
              spacing: Style.space(3)
              Label { text: "OmaStrix"; font.pixelSize: Style.font.heading; font.bold: true }
              Label { text: "Local AI for Strix Halo"; opacity: 0.65 }
            }
            Label {
              id: hardwareWarning
              Layout.row: headerLayout.compact ? 1 : 0
              Layout.column: headerLayout.compact ? 0 : 1
              Layout.columnSpan: headerLayout.compact ? 3 : 1
              visible: root.hasSnapshot && !root.halo
              Layout.fillWidth: true
              Layout.minimumWidth: 0
              text: "Hardware Unsupported - strix-llama.cpp will not function"
              color: root.urgent
              font.pixelSize: Style.font.title
              font.bold: true
              wrapMode: Text.Wrap
            }
            Label { Layout.row: 0; Layout.column: headerLayout.compact ? 1 : 2; text: root.payload.app_version || ""; opacity: 0.5; font.pixelSize: Style.font.caption }
            ActionButton { Layout.row: 0; Layout.column: headerLayout.compact ? 2 : 3; text: "Refresh"; onClicked: root.refresh() }
          }

          Feedback {
            width: parent.width
            visible: root.statusError !== ""
            message: root.statusError
            onDismissed: root.statusError = ""
          }

          Label { visible: !root.hasSnapshot; text: "Reading system status…" }

          Pane {
            width: parent.width
            visible: root.hasSnapshot
            content: Column {
              width: parent.width
              spacing: Style.space(16)
              Label { text: "System"; font.pixelSize: Style.font.title; font.bold: true }
              PluginUpdateRow { width: parent.width }
              Divider { width: parent.width }
              ServiceRow { width: parent.width; kind: "engine"; title: "strix-llama.cpp"; info: root.engine }
              Divider { width: parent.width }
              ServiceRow { width: parent.width; kind: "webui"; title: "Open WebUI"; info: root.webui }
              Divider { width: parent.width }

              Column {
                width: parent.width
                spacing: Style.space(9)
                GridLayout {
                  id: gttLayout
                  width: parent.width
                  columns: width < Style.space(700) ? 1 : 2
                  columnSpacing: Style.space(12)
                  rowSpacing: Style.space(8)
                  Column {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    spacing: Style.space(3)
                    Label { width: parent.width; text: "GPU memory"; font.bold: true; wrapMode: Text.Wrap }
                    Label {
                      width: parent.width
                      wrapMode: Text.Wrap
                      text: "GTT  " + View.formatGttUsed(root.payload.gtt_used_gib)
                        + " / " + (root.payload.gtt_total_gib || "—") + " GiB"
                      opacity: 0.65
                    }
                  }
                  Flow {
                    Layout.fillWidth: true
                    Layout.preferredWidth: implicitWidth
                    Layout.minimumWidth: gttLayout.columns === 1 ? 0 : implicitWidth
                    spacing: Style.space(8)
                    Label { text: "Ceiling"; opacity: 0.65; height: implicitHeight + Style.space(14); verticalAlignment: Text.AlignVCenter }
                    Repeater {
                      model: ["64", "96", "110"]
                      ActionButton {
                        id: gttChoice
                        required property string modelData
                        text: modelData + " GiB"
                        selected: String(root.payload.gtt_set) === modelData
                        enabled: !root.busy && !!root.payload.gtt_choices && root.payload.gtt_choices.indexOf(modelData) >= 0
                        tooltipText: enabled ? "Configure the GTT ceiling" : "Requires more system memory"
                        onClicked: root.requestGtt(modelData)
                      }
                    }
                  }
                }
                Rectangle {
                  width: parent.width
                  height: Style.space(4)
                  radius: height / 2
                  color: Qt.alpha(root.foreground, 0.1)
                  Rectangle {
                    width: parent.width * Math.max(0, Math.min(1, (root.payload.gtt_used_gib || 0) / (root.payload.gtt_total_gib || 1)))
                    height: parent.height
                    radius: parent.radius
                    color: Commons.Color.accent
                  }
                }
                Label { visible: root.payload.gtt_pending === true; text: "GTT change pending reboot"; color: Commons.Color.accent }
                Feedback { width: parent.width; scope: "gtt" }
              }
            }
          }

          Pane {
            width: parent.width
            visible: root.hasSnapshot
            content: Column {
              id: modelColumn
              width: parent.width
              readonly property bool stackedActions: width < root.actionsWidth + root.statusWidth + root.numberWidth + root.rowGap * 3 + Style.space(180)
              spacing: Style.space(14)
              RowLayout {
                width: parent.width
                Label { text: "Models"; font.pixelSize: Style.font.title; font.bold: true; Layout.fillWidth: true }
                Label { text: "~/models"; opacity: 0.6; font.pixelSize: Style.font.caption }
              }
              RowLayout {
                width: parent.width
                spacing: Style.space(8)
                TextField {
                  id: linkField
                  Layout.fillWidth: true
                  placeholderText: "HTTPS link to a GGUF file"
                  text: root.addLink
                  foreground: root.foreground
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.body
                  enabled: !root.busy
                  onTextChanged: root.addLink = text
                  onAccepted: root.addModel()
                  Keys.onEscapePressed: keyCatcher.forceActiveFocus()
                }
                ActionButton { text: "Add model"; enabled: !root.busy && root.addLink.trim() !== ""; onClicked: root.addModel() }
              }
              Feedback { width: parent.width; scope: "add" }

              // The same column widths are used by the header and every row.
              RowLayout {
                visible: !modelColumn.stackedActions
                width: parent.width
                spacing: root.rowGap
                Label { text: "Model"; opacity: 0.6; Layout.fillWidth: true }
                Label { text: "Status"; opacity: 0.6; Layout.preferredWidth: root.statusWidth }
                Label { text: "Params"; opacity: 0.6; Layout.preferredWidth: root.numberWidth; visible: modelColumn.width > Style.space(900) }
                Label { text: "Size"; opacity: 0.6; Layout.preferredWidth: root.numberWidth }
                Label { text: "RAM"; opacity: 0.6; Layout.preferredWidth: root.numberWidth; visible: modelColumn.width > Style.space(800) }
                Label { text: "Actions"; opacity: 0.6; Layout.preferredWidth: root.actionsWidth }
              }
              Divider { width: parent.width }
              Repeater {
                model: root.models
                delegate: Column {
                  id: modelRow
                  required property var modelData
                  required property int index
                  readonly property var primary: View.modelAction(modelData, root.halo && root.engine.state === "running")
                  width: modelColumn.width
                  spacing: Style.space(9)

                  GridLayout {
                    width: parent.width
                    columns: modelColumn.stackedActions ? 1 : 2
                    columnSpacing: root.rowGap
                    rowSpacing: Style.space(9)
                    GridLayout {
                      Layout.fillWidth: true
                      Layout.minimumWidth: 0
                      columns: modelColumn.stackedActions ? 2 : 5
                      rowSpacing: Style.space(4)
                      columnSpacing: root.rowGap
                      Column {
                        Layout.columnSpan: modelColumn.stackedActions ? 2 : 1
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        spacing: Style.space(4)
                        Label { width: parent.width; text: modelRow.modelData.name; elide: Text.ElideRight; font.bold: modelRow.modelData.status_label === "Loaded" || modelRow.modelData.status_label === "Inferring" }
                        Label {
                          width: parent.width
                          text: [modelRow.modelData.quant || "", modelRow.modelData.recommended ? "Recommended" : (modelRow.modelData.test ? "Test model" : "")].filter(Boolean).join(" · ")
                          visible: text !== ""
                          opacity: 0.6
                          font.pixelSize: Style.font.caption
                          elide: Text.ElideRight
                        }
                        PanelToolTip { visible: modelHover.hovered; text: modelRow.modelData.name; fontFamily: root.fontFamily }
                        HoverHandler { id: modelHover }
                      }
                      Label {
                        Layout.preferredWidth: root.statusWidth
                        text: modelRow.modelData.status_label || "—"
                        color: modelRow.modelData.status_label === "Loaded" || modelRow.modelData.status_label === "Inferring" ? Commons.Color.accent : root.foreground
                        opacity: modelRow.modelData.installed ? 1 : 0.6
                      }
                      Label { Layout.preferredWidth: root.numberWidth; text: modelRow.modelData.params || "—"; visible: !modelColumn.stackedActions && modelColumn.width > Style.space(900) }
                      Label { Layout.preferredWidth: root.numberWidth; text: modelRow.modelData.size || "—" }
                      Label { Layout.preferredWidth: root.numberWidth; text: modelRow.modelData.ram || "—"; visible: !modelColumn.stackedActions && modelColumn.width > Style.space(800) }
                    }
                    Row {
                      Layout.preferredWidth: root.actionsWidth
                      Layout.alignment: Qt.AlignLeft
                      spacing: Style.space(8)
                      ActionButton {
                        width: root.modelPrimaryWidth
                        focusKey: "primary:" + modelRow.modelData.id
                        text: root.busy && root.actionScope === modelRow.modelData.id ? "Working…" : modelRow.primary.text
                        actionContext: modelRow.modelData.name
                        enabled: !root.busy && modelRow.primary.enabled
                        tooltipText: {
                          if (modelRow.modelData.status === "downloading") return "Download in progress"
                          if (!modelRow.modelData.fits && modelRow.modelData.installed) return "This model exceeds the memory budget"
                          if (modelRow.modelData.installed && root.engine.state !== "running") return "Start strix-llama.cpp to load a model"
                          return ""
                        }
                        onClicked: root.runAction([modelRow.primary.verb, modelRow.modelData.id], modelRow.modelData.id)
                      }
                      ActionButton {
                        width: root.modelDeleteWidth
                        focusKey: "delete:" + modelRow.modelData.id
                        text: "Delete"
                        actionContext: modelRow.modelData.name
                        visible: modelRow.modelData.deletable === true
                        enabled: !root.busy && modelRow.modelData.status !== "downloading"
                        onClicked: root.runAction(["library-delete", modelRow.modelData.id], modelRow.modelData.id)
                      }
                    }
                  }
                  Column {
                    width: parent.width
                    spacing: Style.space(5)
                    visible: modelRow.modelData.status === "downloading" || (!modelRow.modelData.fits && modelRow.modelData.notes)
                    Rectangle {
                      visible: modelRow.modelData.status === "downloading"
                      width: parent.width
                      height: Style.space(4)
                      color: Qt.alpha(root.foreground, 0.1)
                      Rectangle { width: parent.width * Math.max(0, Math.min(1, (modelRow.modelData.progress || 0) / 100)); height: parent.height; color: Commons.Color.accent }
                    }
                    Label { width: parent.width; text: modelRow.modelData.notes || ""; wrapMode: Text.Wrap; opacity: 0.65; font.pixelSize: Style.font.caption }
                  }
                  Feedback { width: parent.width; scope: modelRow.modelData.id }
                  Divider { width: parent.width; visible: modelRow.index < root.models.length - 1 }
                }
              }
            }
          }
        }
      }
    }
  }

  component Label: Text {
    color: root.foreground
    font.family: root.fontFamily
    font.pixelSize: Style.font.body
    textFormat: Text.PlainText
  }

  component Divider: Rectangle {
    height: 1
    color: root.paneBorder
  }

  component Pane: BorderSurface {
    id: pane
    property Item content
    padding: Style.space(18)
    color: "transparent"
    radius: Style.cornerRadius
    borderSpec: Border.flat(root.paneBorder, 1)
    implicitHeight: content ? content.implicitHeight + contentTopInset + contentBottomInset : 0
    height: implicitHeight
    onContentChanged: if (content) content.parent = body
    Item {
      id: body
      x: pane.contentLeftInset
      y: pane.contentTopInset
      width: pane.width - pane.contentLeftInset - pane.contentRightInset
      height: pane.content ? pane.content.implicitHeight : 0
    }
  }

  component Feedback: Column {
    id: feedback
    property string scope: ""
    property string message: root.messageFor(scope)
    readonly property bool confirming: scope !== "" && root.confirmation.scope === scope
    signal dismissed()
    visible: message !== "" || confirming
    spacing: Style.space(8)
    RowLayout {
      width: parent.width
      spacing: Style.space(12)
      Label {
        Layout.fillWidth: true
        text: feedback.confirming ? root.confirmation.text : feedback.message
        color: feedback.confirming ? root.foreground : root.urgent
        wrapMode: Text.Wrap
      }
      ActionButton { visible: feedback.confirming; text: "Confirm"; focusKey: "confirm:" + feedback.scope; enabled: !root.busy; onClicked: root.confirmAction() }
      ActionButton {
        text: feedback.confirming ? "Cancel" : "Dismiss"
        focusKey: "feedback:" + feedback.scope
        onClicked: {
          if (feedback.confirming) root.confirmation = ({})
          else { root.dismiss(feedback.scope); feedback.dismissed() }
        }
      }
    }
  }

  component PluginUpdateRow: Column {
    id: pluginRow
    readonly property string title: "OmaStrix"
    spacing: Style.space(10)
    GridLayout {
      width: parent.width
      columns: pluginRow.width < Style.space(800) ? 1 : 2
      columnSpacing: Style.space(12)
      rowSpacing: Style.space(10)
      Column {
        Layout.fillWidth: true
        Layout.minimumWidth: 0
        spacing: Style.space(4)
        Label { text: pluginRow.title; font.bold: true }
        Label {
          width: parent.width
          text: View.pluginDetail(root.pluginInfo, root.payload.app_version)
          wrapMode: Text.Wrap
          opacity: 0.65
          font.pixelSize: Style.font.caption
        }
      }
      Row {
        Layout.alignment: Qt.AlignLeft
        spacing: Style.space(8)
        ActionButton {
          width: root.serviceCheckWidth
          text: root.busy && root.actionArgs[0] === "plugin-check" ? "Checking…" : "Check updates"
          actionContext: pluginRow.title
          enabled: !root.busy && !root.pluginInfo.updating && root.pluginInfo.managed === true
          tooltipText: root.pluginInfo.managed === false ? "Requires an installed Git checkout" : "Check for OmaStrix updates"
          onClicked: root.runAction(["plugin-check"], "plugin")
        }
        Item {
          width: root.serviceUpdateWidth
          height: pluginUpdate.implicitHeight
          ActionButton {
            id: pluginUpdate
            anchors.fill: parent
            visible: root.pluginInfo.update_available === true || root.pluginInfo.updating === true
            text: root.pluginInfo.updating ? "Updating…" : "Update"
            actionContext: pluginRow.title
            enabled: !root.busy && !root.pluginInfo.updating && root.pluginInfo.update_available === true
            tooltipText: "Update OmaStrix using Omarchy's plugin updater"
            onClicked: root.runAction(["plugin-update"], "plugin")
          }
        }
      }
    }
    Feedback { width: parent.width; scope: "plugin" }
  }

  component ServiceRow: Column {
    id: service
    required property string kind
    required property string title
    required property var info
    readonly property bool isEngine: kind === "engine"
    readonly property bool running: isEngine ? info.state === "running" : info.running === true
    readonly property var presentation: View.serviceState(info)
    readonly property bool unsupportedStart: isEngine && !root.halo && info.installed === true && !running
    readonly property bool working: presentation.working
    readonly property string stateText: presentation.text
    spacing: Style.space(10)
    GridLayout {
      id: serviceLayout
      width: parent.width
      columns: service.width < Style.space(800) ? 1 : 2
      columnSpacing: Style.space(12)
      rowSpacing: Style.space(10)
      Column {
        Layout.fillWidth: true
        Layout.minimumWidth: 0
        spacing: Style.space(4)
        Label { width: parent.width; text: service.title; font.bold: true; elide: Text.ElideRight }
        Label {
          width: parent.width
          text: View.serviceDetail(service.info, service.isEngine)
          visible: text !== ""
          opacity: 0.65
          font.pixelSize: Style.font.caption
          wrapMode: Text.Wrap
        }
      }
      Flow {
        Layout.fillWidth: true
        Layout.minimumWidth: serviceLayout.columns === 1 ? 0 : naturalWidth
        Layout.preferredWidth: naturalWidth
        spacing: Style.space(8)
        readonly property real naturalWidth: Style.space(110) + root.servicePrimaryWidth + serviceOpen.implicitWidth
          + root.serviceCheckWidth + root.serviceUpdateWidth + spacing * 4
        Label {
          width: Style.space(110)
          height: servicePrimary.height
          verticalAlignment: Text.AlignVCenter
          text: service.stateText
          color: service.running ? Commons.Color.accent : root.foreground
          opacity: service.running ? 1 : 0.65
        }
        ActionButton {
          id: servicePrimary
          actionContext: service.title
          width: root.servicePrimaryWidth
          text: root.busy && root.actionScope === service.kind && root.actionArgs[0] !== service.kind + "-check" ? "Working…" : (!service.info.installed ? "Install" : service.running ? "Stop" : "Start")
          enabled: !root.busy && service.presentation.primaryEnabled && !service.unsupportedStart
          foreground: service.unsupportedStart ? root.urgent : Commons.Color.foreground
          borderSpec: service.unsupportedStart ? Border.flat(root.urgent, 1) : _borderSpec
          background: service.unsupportedStart ? Qt.alpha(root.urgent, 0.12) : Style.normalFillFor(foreground)
          tooltipText: service.unsupportedStart ? "Hardware Unsupported - strix-llama.cpp will not function" : ""
          onClicked: root.runAction([service.kind + (!service.info.installed ? "-install" : service.running ? "-stop" : "-start")], service.kind)
        }
        ActionButton {
          id: serviceOpen
          actionContext: service.title
          text: "Open"
          enabled: service.running
          tooltipText: service.isEngine ? "Open the engine interface" : "Open WebUI"
          onClicked: if (root.bar) root.bar.run(service.isEngine ? "xdg-open http://127.0.0.1:8080" : "xdg-open http://127.0.0.1:3000")
        }
        ActionButton {
          id: serviceCheck
          actionContext: service.title
          width: root.serviceCheckWidth
          text: root.busy && root.actionScope === service.kind && root.actionArgs[0] === service.kind + "-check" ? "Checking…" : "Check updates"
          enabled: service.info.installed === true && !root.busy && !service.working
          onClicked: root.runAction([service.kind + "-check"], service.kind)
        }
        Item {
          // Keep both service action columns aligned when just one has an update.
          width: root.serviceUpdateWidth
          height: servicePrimary.height
          ActionButton {
            anchors.fill: parent
            visible: service.info.update_available === true
            text: "Update"
            actionContext: service.title
            enabled: !root.busy && service.presentation.stopped && !service.working
            tooltipText: service.running ? "Stop " + service.title + " to update" : "Install the available update"
            onClicked: root.runAction([service.kind + "-update"], service.kind)
          }
        }
      }
    }
    Label { width: parent.width; wrapMode: Text.Wrap; visible: service.info.update_available === true && service.running; text: "Stop " + service.title + " to update."; opacity: 0.65 }
    Flow {
      width: parent.width
      visible: !service.isEngine && service.info.installed === true
      spacing: Style.space(8)
      Label { text: "Access"; height: localAccess.height; verticalAlignment: Text.AlignVCenter; opacity: 0.65 }
      ActionButton {
        id: localAccess
        text: "This device"
        actionContext: service.title
        selected: service.info.access === "local"
        enabled: !root.busy && service.presentation.stopped && !service.working && !selected
        tooltipText: service.running ? "Stop Open WebUI to change access" : "Only this device can connect"
        onClicked: root.runAction(["webui-access", "local"], service.kind)
      }
      ActionButton {
        text: "Local network"
        actionContext: service.title
        selected: service.info.access === "network"
        enabled: !root.busy && service.presentation.stopped && !service.working && !selected
        tooltipText: service.running ? "Stop Open WebUI to change access" : "Allow other devices after creating an administrator account"
        onClicked: root.runAction(["webui-access", "network"], service.kind)
      }
    }
    Feedback { width: parent.width; scope: service.kind }
  }
}

import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

Panel {
  id: root
  moduleName: "silexmachina.omastrix"
  ipcTarget: "silexmachina.omastrix"
  manageIpc: true

  property var payload: ({})
  property string errorText: ""
  property bool settingGtt: false

  readonly property color foreground: bar ? bar.foreground : Color.foreground
  readonly property color urgent: bar ? bar.urgent : Color.urgent
  readonly property color dim: Qt.darker(foreground, 1.55)
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family
  readonly property bool halo: payload.strix_halo === true
  readonly property bool gttDefault: payload.gtt_default === true
  readonly property bool pending: payload.gtt_pending === true
  readonly property string gttSet: payload.gtt_set || ""
  readonly property string resetTip: "This change will not take place until after reset."
  readonly property string pillText: payload.pill || "GTT ?"
  readonly property string usedText: payload.gtt_used_gib === undefined || payload.gtt_used_gib === null
    ? "—" : payload.gtt_used_gib + " GiB"

  readonly property var gttOptions: [
    { value: "64", label: "64 GB", tooltip: root.tipFor("64") },
    { value: "96", label: "96 GB", tooltip: root.tipFor("96") },
    { value: "110", label: "110 GB", tooltip: root.tipFor("110") }
  ]

  function tipFor(value) {
    if (gttSet === value && (pending || settingGtt))
      return resetTip
    return ""
  }

  function setting(name, fallback) {
    var value = settings ? settings[name] : undefined
    return value === undefined || value === null ? fallback : value
  }

  function scriptPath() {
    var url = Qt.resolvedUrl("bin/omastrix").toString()
    if (url.indexOf("file://") === 0)
      url = decodeURIComponent(url.slice(7))
    return url
  }

  function refresh() {
    if (proc.running)
      return
    proc.command = [scriptPath(), "snapshot"]
    proc.running = true
  }

  function apply(raw) {
    try {
      payload = JSON.parse(String(raw || "").trim())
      errorText = ""
    } catch (e) {
      errorText = "status parse failed"
    }
  }

  function chooseGtt(value) {
    if (settingGtt || value === gttSet)
      return
    errorText = ""
    settingGtt = true
    setProc.command = ["pkexec", scriptPath(), "set-gtt", value]
    setProc.running = true
  }

  function finishSet(raw, err) {
    settingGtt = false
    var msg = String(err || "").trim()
    var body = String(raw || "").trim()
    if (body.indexOf("\"success\":true") >= 0 || body.indexOf("\"success\": true") >= 0) {
      errorText = ""
      refresh()
      if (bar)
        bar.showTooltip(gttRow, resetTip)
      return
    }
    if (msg !== "")
      errorText = msg
    else if (body !== "")
      errorText = body
    else
      errorText = "GTT change was not applied"
    refresh()
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  Component.onCompleted: refresh()

  Timer {
    interval: root.opened ? 2000 : Math.max(2, Number(root.setting("refreshIntervalSec", 5))) * 1000
    running: true
    repeat: true
    triggeredOnStart: false
    onTriggered: root.refresh()
  }

  Process {
    id: proc
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.apply(text)
    }
    stderr: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        var msg = String(text || "").trim()
        if (msg !== "")
          root.errorText = msg
      }
    }
  }

  Process {
    id: setProc
    stdout: StdioCollector {
      id: setOut
      waitForEnd: true
    }
    stderr: StdioCollector {
      id: setErr
      waitForEnd: true
    }
    onRunningChanged: if (!running) root.finishSet(setOut.text, setErr.text)
  }

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: root.pillText
    active: !root.halo || root.gttDefault || root.errorText !== ""
    fontSize: Style.font.title
    horizontalMargin: 8.75
    tooltipText: root.errorText !== "" ? root.errorText
      : (root.pending ? root.resetTip : "OmaStrix  GTT " + root.pillText)
    onPressed: function(buttonCode) {
      if (buttonCode === Qt.MiddleButton)
        root.refresh()
      else
        root.toggle()
    }
  }

  KeyboardPanel {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(980))
    contentHeight: panel.fittedContentHeight(column.implicitHeight, Style.space(160))

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      onCloseRequested: root.close()
      onActivateRequested: root.refresh()
      onTabRequested: function(direction) { root.switchPanel(direction) }

      Column {
        id: column
        width: parent.width
        spacing: Style.space(12)

        PanelHero {
          width: parent.width
          title: "OmaStrix"
          meta: root.halo ? "Strix Halo" : "Not this host"
          foreground: root.halo ? root.foreground : root.urgent
          fontFamily: root.fontFamily
        }

        Row {
          id: gttRow
          width: parent.width
          spacing: Style.space(10)

          Text {
            text: "GTT"
            color: root.foreground
            font.family: root.fontFamily
            font.pixelSize: Style.font.title
            font.bold: true
            textFormat: Text.PlainText
            anchors.verticalCenter: parent.verticalCenter
          }

          Text {
            text: "Used: " + root.usedText
            color: root.foreground
            font.family: root.fontFamily
            font.pixelSize: Style.font.title
            textFormat: Text.PlainText
            anchors.verticalCenter: parent.verticalCenter
          }

          Text {
            text: "/"
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.title
            textFormat: Text.PlainText
            anchors.verticalCenter: parent.verticalCenter
          }

          Text {
            text: "Max:"
            color: root.foreground
            font.family: root.fontFamily
            font.pixelSize: Style.font.title
            textFormat: Text.PlainText
            anchors.verticalCenter: parent.verticalCenter
          }

          ButtonGroup {
            id: maxBoxes
            fontSize: Style.font.title
            fontFamily: root.fontFamily
            foreground: root.foreground
            accent: Color.accent
            options: root.gttOptions
            value: root.gttSet
            enabled: !root.settingGtt
            onChanged: root.chooseGtt(value)
            anchors.verticalCenter: parent.verticalCenter
          }

          Text {
            visible: root.pending
            text: "GTT Change Pending Reboot"
            color: root.urgent
            font.family: root.fontFamily
            font.pixelSize: Style.font.title
            font.bold: true
            textFormat: Text.PlainText
            anchors.verticalCenter: parent.verticalCenter
          }
        }

        Text {
          width: parent.width
          visible: root.errorText !== ""
          wrapMode: Text.Wrap
          text: root.errorText
          color: root.urgent
          font.family: root.fontFamily
          font.pixelSize: Style.font.body
          textFormat: Text.PlainText
        }
      }
    }
  }
}

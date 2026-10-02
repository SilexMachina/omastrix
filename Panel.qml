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

  readonly property color foreground: bar ? bar.foreground : Color.foreground
  readonly property color urgent: bar ? bar.urgent : Color.urgent
  readonly property color dim: Qt.darker(foreground, 1.55)
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family
  readonly property bool halo: payload.strix_halo === true
  readonly property bool gttDefault: payload.gtt_default === true
  readonly property bool alarm: !halo || gttDefault || errorText !== ""
  readonly property string pillText: payload.pill || "GTT ?"

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

  function gib(value) {
    return value === undefined || value === null ? "—" : value
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

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: root.pillText
    active: root.alarm
    fontSize: 12
    tooltipText: root.errorText !== "" ? root.errorText
      : (root.halo ? "OmaStrix  GTT " + root.pillText : "OmaStrix  not Strix Halo")
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
    contentWidth: panel.fittedContentWidth(Style.space(420))
    contentHeight: panel.fittedContentHeight(column.implicitHeight, Style.space(280))

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      onCloseRequested: root.close()
      onActivateRequested: root.refresh()
      onTabRequested: function(direction) { root.switchPanel(direction) }
      onTextKey: function(t) { if (t === "r" || t === "R") root.refresh() }

      Column {
        id: column
        width: parent.width
        spacing: Style.space(10)

        PanelHero {
          width: parent.width
          title: "OmaStrix"
          meta: root.halo ? "Strix Halo" : "Not this host"
          detail: root.gttDefault ? "GTT is still the kernel default" : "GTT ceiling is raised"
          foreground: root.alarm ? root.urgent : root.foreground
          fontFamily: root.fontFamily
        }

        PanelSeparator { foreground: root.foreground }

        PanelSectionHeader {
          text: "GTT"
          foreground: root.foreground
          fontFamily: root.fontFamily
        }

        Text {
          width: parent.width
          text: root.gib(root.payload.gtt_used_gib) + " / " + root.gib(root.payload.gtt_total_gib) + " GiB"
          color: root.gttDefault ? root.urgent : root.foreground
          font.family: root.fontFamily
          font.pixelSize: Style.font.body
          textFormat: Text.PlainText
        }

        Text {
          width: parent.width
          wrapMode: Text.Wrap
          text: root.gttDefault
            ? "The ceiling is the kernel default. A later setup step can offer a raise. It will not change the boot line without a confirm."
            : "Used and ceiling. The library, when it exists, will fit models against this ceiling."
          color: root.dim
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          textFormat: Text.PlainText
        }

        PanelSectionHeader {
          text: "Host"
          foreground: root.foreground
          fontFamily: root.fontFamily
        }

        Text {
          width: parent.width
          wrapMode: Text.Wrap
          text: root.payload.gpu_name || "No amdgpu GTT device"
          color: root.foreground
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          textFormat: Text.PlainText
        }

        Text {
          width: parent.width
          text: "RAM " + root.gib(root.payload.mem_total_gib) + " GiB    " + (root.payload.pci || "")
          color: root.dim
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          textFormat: Text.PlainText
        }

        Text {
          width: parent.width
          visible: root.errorText !== ""
          wrapMode: Text.Wrap
          text: root.errorText
          color: root.urgent
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          textFormat: Text.PlainText
        }

        Text {
          width: parent.width
          wrapMode: Text.Wrap
          text: "No model library in this cut. Nothing is downloaded."
          color: root.dim
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          textFormat: Text.PlainText
        }
      }
    }
  }
}

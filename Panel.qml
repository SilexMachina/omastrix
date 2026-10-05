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
  property bool engineBusy: false
  property string pendingLoad: ""
  property bool showTooLarge: false
  property string updateNote: ""

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
  readonly property var engine: payload.engine || ({})
  readonly property string engineState: engine.state || "not_installed"
  readonly property string engineLabel: {
    if (engineState === "running") return "Running"
    if (engineState === "starting") return "Starting"
    if (engineState === "failed") return "Failed"
    if (engineState === "stopped") return "Stopped"
    return "Not installed"
  }
  readonly property string installedText: engine.installed === true ? "Yes" : "No"
  readonly property string versionText: {
    var raw = String(engine.version || "")
    var cut = raw.indexOf(", commit")
    if (cut >= 0)
      raw = raw.substring(0, cut) + ")"
    return raw === "" ? "—" : raw
  }
  readonly property var fitting: (payload.library && payload.library.fitting) ? payload.library.fitting : []
  readonly property var tooLarge: (payload.library && payload.library.too_large) ? payload.library.too_large : []
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

  function runEngine(args) {
    if (engineBusy)
      return
    engineBusy = true
    errorText = ""
    engineProc.command = [scriptPath()].concat(args)
    engineProc.running = true
  }

  function finishEngine(raw, err) {
    engineBusy = false
    var body = String(raw || "").trim()
    var msg = String(err || "").trim()
    if (body.charAt(0) === "{") {
      try {
        var info = JSON.parse(body)
        if (info.needs_confirm) {
          pendingLoad = info.id || ""
          errorText = info.error || "Confirm the load."
          refresh()
          return
        }
        if (info.matches_pin !== undefined) {
          pendingLoad = ""
          if (info.matches_pin)
            updateNote = "Installed build matches the approved pin."
              + (info.latest_tag ? " Newest published Halo build tag: " + info.latest_tag + ". That tag is not installed until the pin changes." : "")
          else if (info.latest_tag)
            updateNote = "Installed build is not the approved pin. Newest published Halo build tag: " + info.latest_tag
          else
            updateNote = "Could not read a newer tag."
          errorText = ""
          refresh()
          return
        }
        pendingLoad = ""
        if (info.success === false)
          errorText = info.error || "That did not work."
        else {
          errorText = ""
          if (info.message)
            updateNote = info.message
        }
        refresh()
        return
      } catch (e) {
        errorText = "status parse failed"
      }
    } else if (msg !== "") {
      errorText = msg
    }
    refresh()
  }

  function loadModel(id) {
    if (pendingLoad === id)
      runEngine(["library-load", id, "--confirm"])
    else
      runEngine(["library-load", id])
  }

  function openInterface() {
    if (engineState !== "running") {
      errorText = "Start strix-llama.cpp before opening its interface."
      return
    }
    if (bar)
      bar.run("xdg-open http://127.0.0.1:8080")
  }

  function toggleAutostart() {
    runEngine(["engine-autostart", engine.autostart ? "off" : "on"])
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
    id: engineProc
    stdout: StdioCollector { id: engineOut; waitForEnd: true }
    stderr: StdioCollector { id: engineErr; waitForEnd: true }
    onRunningChanged: if (!running) root.finishEngine(engineOut.text, engineErr.text)
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
    contentWidth: panel.fittedContentWidth(Style.space(1180))
    contentHeight: panel.fittedContentHeight(column.implicitHeight, Style.space(1100))

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

        Row {
          id: engineRow
          width: parent.width
          spacing: Style.space(10)

          Text {
            text: "strix-llama.cpp"
            color: root.foreground
            font.family: root.fontFamily
            font.pixelSize: Style.font.title
            font.bold: true
            textFormat: Text.PlainText
            anchors.verticalCenter: parent.verticalCenter
          }

          Text {
            text: "Installed:"
            color: root.foreground
            font.family: root.fontFamily
            font.pixelSize: Style.font.title
            textFormat: Text.PlainText
            anchors.verticalCenter: parent.verticalCenter
          }

          Text {
            text: root.installedText
            color: root.engine.installed === true ? root.foreground : root.urgent
            font.family: root.fontFamily
            font.pixelSize: Style.font.title
            font.bold: true
            textFormat: Text.PlainText
            anchors.verticalCenter: parent.verticalCenter
          }

          Text {
            visible: root.engine.installed === true
            text: "Version:"
            color: root.foreground
            font.family: root.fontFamily
            font.pixelSize: Style.font.title
            textFormat: Text.PlainText
            anchors.verticalCenter: parent.verticalCenter
          }

          Text {
            visible: root.engine.installed === true
            text: root.versionText
            color: root.foreground
            font.family: root.fontFamily
            font.pixelSize: Style.font.title
            textFormat: Text.PlainText
            anchors.verticalCenter: parent.verticalCenter
          }

          Text {
            visible: root.engine.installed === true
            text: "Status:"
            color: root.foreground
            font.family: root.fontFamily
            font.pixelSize: Style.font.title
            textFormat: Text.PlainText
            anchors.verticalCenter: parent.verticalCenter
          }

          Text {
            visible: root.engine.installed === true
            text: root.engineLabel
            color: root.engineState === "failed" ? root.urgent : root.foreground
            font.family: root.fontFamily
            font.pixelSize: Style.font.title
            font.bold: true
            textFormat: Text.PlainText
            anchors.verticalCenter: parent.verticalCenter
          }
        }

        Row {
          spacing: Style.space(8)

          Button {
            text: "Start"
            fontSize: Style.font.title
            fontFamily: root.fontFamily
            foreground: root.foreground
            enabled: root.engineState === "stopped" && !root.engineBusy
            onClicked: root.runEngine(["engine-start"])
          }
          Button {
            text: "Stop"
            fontSize: Style.font.title
            fontFamily: root.fontFamily
            foreground: root.foreground
            enabled: root.engineState === "running" && !root.engineBusy
            onClicked: root.runEngine(["engine-stop"])
          }
          Button {
            text: "Open interface"
            fontSize: Style.font.title
            fontFamily: root.fontFamily
            foreground: root.foreground
            enabled: root.engineState === "running"
            onClicked: root.openInterface()
          }
          Button {
            text: root.engine.autostart ? "Logon start: On" : "Logon start: Off"
            fontSize: Style.font.title
            fontFamily: root.fontFamily
            foreground: root.foreground
            enabled: root.engine.installed === true && !root.engineBusy
            onClicked: root.toggleAutostart()
          }
          Button {
            text: "Check updates"
            fontSize: Style.font.title
            fontFamily: root.fontFamily
            foreground: root.foreground
            enabled: !root.engineBusy
            onClicked: root.runEngine(["engine-check"])
          }
        }

        Text {
          width: parent.width
          visible: root.engine.installed === true
          wrapMode: Text.Wrap
          text: "Start runs the service with no model loaded. Load is a separate click. Download does not load."
          color: root.dim
          font.family: root.fontFamily
          font.pixelSize: Style.font.body
          textFormat: Text.PlainText
        }

        Text {
          width: parent.width
          text: "Models"
          color: root.foreground
          font.family: root.fontFamily
          font.pixelSize: Style.font.title
          font.bold: true
          textFormat: Text.PlainText
        }

        Repeater {
          model: root.fitting
          delegate: Column {
            width: column.width
            spacing: Style.space(4)

            Text {
              width: parent.width
              wrapMode: Text.Wrap
              text: modelData.name
                + (modelData.recommended ? "  Recommended" : "")
                + (modelData.test ? "  Test model" : "")
                + "  " + modelData.quant
              color: root.foreground
              font.family: root.fontFamily
              font.pixelSize: Style.font.title
              font.bold: true
              textFormat: Text.PlainText
            }

            Text {
              width: parent.width
              wrapMode: Text.Wrap
              text: "Installed: " + (modelData.installed ? "Yes" : "No")
                + "   Size: " + modelData.size_gib + " GiB"
                + "   Status: " + (modelData.server_status === "loaded" ? "Loaded" : modelData.server_status === "loading" ? "Loading" : "Not loaded")
              color: root.foreground
              font.family: root.fontFamily
              font.pixelSize: Style.font.title
              textFormat: Text.PlainText
            }

            Text {
              width: parent.width
              visible: true
              wrapMode: Text.Wrap
              text: modelData.tags.join(", ") + (modelData.speed ? "   " + modelData.speed : "")
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.body
              textFormat: Text.PlainText
            }

            Text {
              width: parent.width
              visible: modelData.server_status === "loaded"
              wrapMode: Text.Wrap
              text: root.payload.library && root.payload.library.tokens_since_load !== null && root.payload.library.tokens_since_load !== undefined
                ? "Tokens since load: " + root.payload.library.tokens_since_load
                : "Token count unavailable"
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.body
              textFormat: Text.PlainText
            }

            Row {
              spacing: Style.space(8)

              Button {
                text: modelData.status === "downloading" ? "Downloading" : "Download"
                fontSize: Style.font.title
                fontFamily: root.fontFamily
                foreground: root.foreground
                visible: !modelData.installed
                enabled: modelData.status !== "downloading" && !root.engineBusy
                onClicked: root.runEngine(["library-download", modelData.id])
              }
              Button {
                text: "Load"
                fontSize: Style.font.title
                fontFamily: root.fontFamily
                foreground: root.foreground
                visible: modelData.installed && modelData.server_status !== "loaded"
                enabled: modelData.fits && root.engineState === "running" && !root.engineBusy
                onClicked: root.loadModel(modelData.id)
              }
              Button {
                text: "Unload"
                fontSize: Style.font.title
                fontFamily: root.fontFamily
                foreground: root.foreground
                visible: modelData.server_status === "loaded"
                enabled: !root.engineBusy
                onClicked: root.runEngine(["library-unload", modelData.id])
              }
            }
          }
        }

        Button {
          text: root.showTooLarge ? "Hide models too large for this system" : "Show models too large for this system"
          fontSize: Style.font.title
          fontFamily: root.fontFamily
          foreground: root.foreground
          visible: root.tooLarge.length > 0
          onClicked: root.showTooLarge = !root.showTooLarge
        }

        Repeater {
          model: root.showTooLarge ? root.tooLarge : []
          delegate: Column {
            width: column.width
            spacing: Style.space(4)

            Text {
              width: parent.width
              wrapMode: Text.Wrap
              text: modelData.name + "   Installed: " + (modelData.installed ? "Yes" : "No")
                + "   Size: " + modelData.size_gib + " GiB   Too large by " + modelData.shortfall_gib + " GiB"
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.title
              textFormat: Text.PlainText
            }
          }
        }

        Text {
          width: parent.width
          visible: root.updateNote !== ""
          wrapMode: Text.Wrap
          text: root.updateNote
          color: root.dim
          font.family: root.fontFamily
          font.pixelSize: Style.font.body
          textFormat: Text.PlainText
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

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
  property string updateNote: ""
  property string addLink: ""

  readonly property color foreground: bar ? bar.foreground : Color.foreground
  readonly property color urgent: bar ? bar.urgent : Color.urgent
  readonly property color dim: Qt.darker(foreground, 1.55)
  readonly property color paneBorder: Qt.rgba(foreground.r, foreground.g, foreground.b, 0.55)
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family
  readonly property bool halo: payload.strix_halo === true
  readonly property bool gttDefault: payload.gtt_default === true
  readonly property bool pending: payload.gtt_pending === true
  readonly property string gttSet: payload.gtt_set || ""
  readonly property string resetTip: "This change will not take place until after reset."
  readonly property string pillText: payload.pill || "GTT ?"
  readonly property var engine: payload.engine || ({})
  readonly property var webui: payload.webui || ({})
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
  readonly property string usedText: payload.gtt_used_gib === undefined || payload.gtt_used_gib === null
    ? "—" : payload.gtt_used_gib + " GiB"
  readonly property var models: (payload.library && payload.library.rows) ? payload.library.rows : []
  readonly property int colModel: Style.space(230)
  readonly property int colStatus: Style.space(140)
  readonly property int colParams: Style.space(110)
  readonly property int colSize: Style.space(90)
  readonly property int colRam: Style.space(100)
  readonly property int colEngine: Style.space(170)
  readonly property int colNotes: Style.space(240)
  readonly property int colAction: Style.space(120)

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
    if (body.indexOf("\"success\",true") >= 0 || body.indexOf("\"success\": true") >= 0) {
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

  function later(what) {
    updateNote = what + " is not wired yet."
  }

  function addModel() {
    later("Adding a model from a link")
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
    stdout: StdioCollector { id: setOut; waitForEnd: true }
    stderr: StdioCollector { id: setErr; waitForEnd: true }
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
    contentWidth: panel.fittedContentWidth(Style.space(1680))
    contentHeight: panel.fittedContentHeight(column.implicitHeight, Style.space(1280))

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

        Column {
          spacing: Style.space(2)

          Text {
            text: "OmaStrix"
            color: root.halo ? root.foreground : root.urgent
            font.family: root.fontFamily
            font.pixelSize: Style.font.heading
            font.bold: true
            textFormat: Text.PlainText
          }

          Text {
            text: "Local AI for Strix Halo"
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.body
            textFormat: Text.PlainText
          }
        }

        BorderSurface {
          id: systemPane
          width: parent.width
          color: "transparent"
          radius: Style.space(4)
          padding: Style.space(12)
          borderSpec: Border.flat(root.paneBorder, 1)
          implicitHeight: systemColumn.implicitHeight + contentTopInset + contentBottomInset
          height: implicitHeight

          Column {
            id: systemColumn
            x: systemPane.contentLeftInset
            y: systemPane.contentTopInset
            width: systemPane.width - systemPane.contentLeftInset - systemPane.contentRightInset
            spacing: Style.space(8)

            Text {
              text: "System"
              color: root.foreground
              font.family: root.fontFamily
              font.pixelSize: Style.font.title
              font.bold: true
              textFormat: Text.PlainText
            }

            Text {
              width: parent.width
              wrapMode: Text.Wrap
              text: "strix-llama.cpp  Installed: " + root.installedText
                + "  Version: " + root.versionText
                + "  Status: " + root.engineLabel
              color: root.foreground
              font.family: root.fontFamily
              font.pixelSize: Style.font.title
              textFormat: Text.PlainText
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
                text: "Max:"
                color: root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.title
                textFormat: Text.PlainText
                anchors.verticalCenter: parent.verticalCenter
              }
              ButtonGroup {
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
              spacing: Style.space(8)
              Button {
                text: root.engine.installed === true ? "strrix-llama.cpp installed" : "Install strix-llama.cpp"
                fontSize: Style.font.title
                fontFamily: root.fontFamily
                foreground: root.foreground
                enabled: root.engine.installed !== true && !root.engineBusy
                onClicked: root.later("Install strix-llama.cpp")
              }
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
                text: "Open engine UI"
                fontSize: Style.font.title
                fontFamily: root.fontFamily
                foreground: root.foreground
                enabled: root.engineState === "running"
                onClicked: root.openInterface()
              }
            }

            Text {
              width: parent.width
              text: "Open WebUI  Installed: " + (root.webui.installed === true ? "Yes" : "No")
                + (root.webui.version ? "  Version: " + root.webui.version : "")
                + "  Status: " + (root.webui.state === "installing" ? "Installing" : (root.webui.running === true ? "Running" : "Stopped"))
              color: root.foreground
              font.family: root.fontFamily
              font.pixelSize: Style.font.title
              textFormat: Text.PlainText
            }

            Row {
              spacing: Style.space(8)
              Button {
                text: root.webui.state === "installing" ? "Installing Open WebUI" : "Install Open WebUI"
                fontSize: Style.font.title
                fontFamily: root.fontFamily
                foreground: root.foreground
                enabled: root.webui.installed !== true && root.webui.state !== "installing" && !root.engineBusy
                onClicked: root.runEngine(["webui-install"])
              }
              Button {
                text: "Start Open WebUI"
                fontSize: Style.font.title
                fontFamily: root.fontFamily
                foreground: root.foreground
                enabled: root.webui.installed === true && root.webui.running !== true && !root.engineBusy
                onClicked: root.runEngine(["webui-start"])
              }
              Button {
                text: "Stop Open WebUI"
                fontSize: Style.font.title
                fontFamily: root.fontFamily
                foreground: root.foreground
                enabled: root.webui.running === true && !root.engineBusy
                onClicked: root.runEngine(["webui-stop"])
              }
              Button {
                text: "Open Open WebUI"
                fontSize: Style.font.title
                fontFamily: root.fontFamily
                foreground: root.foreground
                enabled: root.webui.running === true
                onClicked: {
                  if (bar)
                    bar.run("xdg-open http://127.0.0.1:3000")
                }
              }
            }
          }
        }

        BorderSurface {
          id: modelPane
          width: parent.width
          color: "transparent"
          radius: Style.space(4)
          padding: Style.space(12)
          borderSpec: Border.flat(root.paneBorder, 1)
          implicitHeight: modelColumn.implicitHeight + contentTopInset + contentBottomInset
          height: implicitHeight

          Column {
            id: modelColumn
            x: modelPane.contentLeftInset
            y: modelPane.contentTopInset
            width: modelPane.width - modelPane.contentLeftInset - modelPane.contentRightInset
            spacing: Style.space(8)

            Text {
              text: "Models"
              color: root.foreground
              font.family: root.fontFamily
              font.pixelSize: Style.font.title
              font.bold: true
              textFormat: Text.PlainText
            }

            Row {
              spacing: Style.space(8)
              TextField {
                width: Style.space(640)
                placeholderText: "Paste a model link"
                text: root.addLink
                foreground: root.foreground
                font.pixelSize: Style.font.title
                font.family: root.fontFamily
                onTextChanged: root.addLink = text
                onAccepted: root.addModel()
              }
              Button {
                text: "Add model"
                fontSize: Style.font.title
                fontFamily: root.fontFamily
                foreground: root.foreground
                onClicked: root.addModel()
              }
            }

            Row {
              width: parent.width
              spacing: Style.space(8)
              Text { width: root.colModel; text: "Model"; color: root.foreground; font.family: root.fontFamily; font.pixelSize: Style.font.title; font.bold: true; textFormat: Text.PlainText }
              Text { width: root.colStatus; text: "Status"; color: root.foreground; font.family: root.fontFamily; font.pixelSize: Style.font.title; font.bold: true; textFormat: Text.PlainText }
              Text { width: root.colParams; text: "Parameters"; color: root.foreground; font.family: root.fontFamily; font.pixelSize: Style.font.title; font.bold: true; textFormat: Text.PlainText }
              Text { width: root.colSize; text: "Size"; color: root.foreground; font.family: root.fontFamily; font.pixelSize: Style.font.title; font.bold: true; textFormat: Text.PlainText }
              Text { width: root.colRam; text: "RAM"; color: root.foreground; font.family: root.fontFamily; font.pixelSize: Style.font.title; font.bold: true; textFormat: Text.PlainText }
              Text { width: root.colEngine; text: "Engine"; color: root.foreground; font.family: root.fontFamily; font.pixelSize: Style.font.title; font.bold: true; textFormat: Text.PlainText }
              Text { width: root.colNotes; text: "Notes"; color: root.foreground; font.family: root.fontFamily; font.pixelSize: Style.font.title; font.bold: true; textFormat: Text.PlainText }
              Text { width: root.colAction; text: "Action"; color: root.foreground; font.family: root.fontFamily; font.pixelSize: Style.font.title; font.bold: true; textFormat: Text.PlainText }
            }

            Rectangle {
              width: parent.width
              height: 1
              color: root.paneBorder
            }

            Repeater {
              model: root.models
              delegate: Row {
                width: modelColumn.width
                spacing: Style.space(8)
                Text {
                  width: root.colModel
                  text: modelData.name
                  color: root.foreground
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.title
                  elide: Text.ElideRight
                  textFormat: Text.PlainText
                }
                Text {
                  width: root.colStatus
                  text: modelData.status_label || "—"
                  color: modelData.status_label === "Inferring" ? Color.accent : root.foreground
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.title
                  font.bold: modelData.status_label === "Loaded" || modelData.status_label === "Inferring"
                  elide: Text.ElideRight
                  textFormat: Text.PlainText
                }
                Text {
                  width: root.colParams
                  text: modelData.params || "—"
                  color: root.foreground
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.title
                  textFormat: Text.PlainText
                }
                Text {
                  width: root.colSize
                  text: modelData.size || "—"
                  color: root.foreground
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.title
                  textFormat: Text.PlainText
                }
                Text {
                  width: root.colRam
                  text: modelData.ram || "—"
                  color: root.foreground
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.title
                  textFormat: Text.PlainText
                }
                Text {
                  width: root.colEngine
                  text: modelData.engine_name || "—"
                  color: root.foreground
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.title
                  elide: Text.ElideRight
                  textFormat: Text.PlainText
                }
                Text {
                  width: root.colNotes
                  text: modelData.notes || "—"
                  color: root.dim
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.body
                  elide: Text.ElideRight
                  textFormat: Text.PlainText
                  anchors.verticalCenter: parent.verticalCenter
                }
                Button {
                  property string rowId: modelData.id
                  property bool rowInstalled: modelData.installed === true
                  property string rowStatus: modelData.status || ""
                  property string rowLabel: modelData.status_label || ""
                  property bool rowFits: modelData.fits === true
                  text: {
                    if (!rowInstalled)
                      return rowStatus === "downloading" ? "Installing" : "Install"
                    if (rowLabel === "Loaded" || rowLabel === "Inferring")
                      return "Unload"
                    return "Load"
                  }
                  fontSize: Style.font.title
                  fontFamily: root.fontFamily
                  foreground: root.foreground
                  enabled: {
                    if (root.engineBusy)
                      return false
                    if (!rowInstalled)
                      return rowStatus !== "downloading"
                    if (rowLabel === "Loaded" || rowLabel === "Inferring")
                      return true
                    return rowFits
                  }
                  onClicked: {
                    if (!rowInstalled)
                      root.runEngine(["library-download", rowId])
                    else if (rowLabel === "Loaded" || rowLabel === "Inferring")
                      root.runEngine(["library-unload", rowId])
                    else
                      root.loadModel(rowId)
                  }
                }
              }
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

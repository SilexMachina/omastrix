import QtQuick
import QtQuick.Shapes
import qs.Commons as Commons

Item {
  id: root
  objectName: "modelStatusIcon"
  state: "unknown"
  implicitWidth: 22
  implicitHeight: 22
  readonly property color inkColor: state === "active" ? Commons.Color.accent
    : state === "ready" ? "#249666" : Commons.Color.muted
  readonly property bool corners: state === "active"

  Item {
    width: 24
    height: 24
    scale: Math.min(root.width, root.height) / 24
    anchors.centerIn: parent
    Shape {
      anchors.fill: parent
      ShapePath {
        objectName: "chipStroke"
        strokeColor: root.inkColor
        strokeWidth: 1.6
        fillColor: "transparent"
        capStyle: ShapePath.SquareCap
        joinStyle: ShapePath.MiterJoin
        PathSvg { path: "M7 5H17A2 2 0 0 1 19 7V17A2 2 0 0 1 17 19H7A2 2 0 0 1 5 17V7A2 2 0 0 1 7 5Z M9 2v3m6-3v3M9 19v3m6-3v3M2 9h3m-3 6h3M19 9h3m-3 6h3" }
      }
      ShapePath {
        objectName: "letterStroke"
        strokeColor: root.inkColor
        strokeWidth: 1.6
        fillColor: "transparent"
        capStyle: ShapePath.SquareCap
        joinStyle: ShapePath.MiterJoin
        PathSvg { path: "M15 9H9v3h6v3H9" }
      }
    }
    Shape {
      objectName: "activeCorners"
      anchors.fill: parent
      visible: root.corners
      ShapePath {
        strokeColor: root.inkColor
        strokeWidth: 1.6
        fillColor: "transparent"
        PathSvg { path: "M2 2l1.5 1.5M20.5 3.5L22 2M2 22l1.5-1.5M20.5 20.5L22 22" }
      }
    }
  }
}

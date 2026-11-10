import QtQuick
import qs.Commons
import qs.Commons as Commons
import qs.Ui
import "View.js" as View

// Shared affordance for every action in the panel.
Button {
  id: root
  property string actionContext: ""
  property string focusKey: ""
  bordered: true
  focusable: true
  foreground: Commons.Color.foreground
  fontFamily: Style.font.family
  fontSize: Style.font.body
  horizontalPadding: Style.space(12)
  verticalPadding: Style.space(7)
  background: Style.normalFillFor(foreground)
  opacity: enabled ? 1 : 0.4
  Accessible.role: Accessible.Button
  Accessible.name: View.actionName(text, actionContext)
  Accessible.onPressAction: if (enabled) clicked()
}

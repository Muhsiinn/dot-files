pragma ComponentBehavior: Bound

import Quickshell
import Quickshell.Hyprland
import Quickshell.Io
import Quickshell.Wayland
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Anya's dashboard: greeting + uptime, ~/todo.md, and a month calendar.
// Opens from the Waybar Anya image and clock, toggles from the same buttons,
// and dismisses with Escape or by clicking anywhere outside.
PanelWindow {
    id: root

    anchors { top: true }
    margins { top: 8 }
    implicitWidth: 610
    implicitHeight: 416
    color: "transparent"
    visible: false
    focusable: true
    exclusiveZone: 0
    WlrLayershell.namespace: "anya-documentation-zone"
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.OnDemand

    readonly property string backend: "/home/anya/.config/quickshell/anya-documentation-zone/backend.py"

    property bool isOpen: false
    property bool busy: false
    property string errorText: ""
    property int viewMonth: 1
    property int viewYear: 2026
    property var state: ({
        greeting: "Hello",
        message: "Hallo, Anya.",
        uptime: "",
        todos: [],
        total: 0,
        remaining: 0,
        todayDay: 0,
        todayMonth: 1,
        todayYear: 2026,
        dateLabel: ""
    })
    readonly property var todos: root.state.todos || []

    function refresh() {
        if (!stateProc.running) stateProc.running = true;
    }

    function readState(raw) {
        try {
            const parsed = JSON.parse(raw);
            if (parsed && parsed.error) throw new Error(parsed.error);
            root.state = parsed;
            root.errorText = "";
        } catch (error) {
            root.errorText = String(error).replace(/^Error: /, "");
        }
        root.busy = false;
    }

    function toggleTodo(index) {
        if (root.busy) return;
        root.busy = true;
        toggleProc.command = ["python3", root.backend, "toggle", String(index)];
        toggleProc.running = true;
    }

    function shiftMonth(delta) {
        let month = root.viewMonth + delta;
        let year = root.viewYear;
        if (month < 1) { month = 12; year -= 1; }
        if (month > 12) { month = 1; year += 1; }
        root.viewMonth = month;
        root.viewYear = year;
    }

    function monthLabel() {
        const names = ["January", "February", "March", "April", "May", "June",
                       "July", "August", "September", "October", "November", "December"];
        return names[root.viewMonth - 1] + "  " + root.viewYear;
    }

    function openPanel() {
        if (root.isOpen) return;
        root.isOpen = true;
        closeTimer.stop();
        root.errorText = "";
        const now = new Date();
        root.viewMonth = now.getMonth() + 1;
        root.viewYear = now.getFullYear();
        root.visible = true;
        root.refresh();
        panel.opacity = 0;
        panel.scale = 0.985;
        Qt.callLater(function() {
            panel.opacity = 1;
            panel.scale = 1;
            keyCatcher.forceActiveFocus();
        });
    }

    function closePanel() {
        if (!root.isOpen) return;
        root.isOpen = false;
        panel.opacity = 0;
        panel.scale = 0.985;
        closeTimer.restart();
    }

    function toggle() {
        // An outside click dismisses the panel via HyprlandFocusGrab. If the
        // same click also reaches Waybar's button, don't immediately reopen
        // while the close animation is still running.
        if (!root.isOpen && closeTimer.running) return;
        if (root.isOpen) root.closePanel();
        else root.openPanel();
    }

    IpcHandler {
        target: "dashboard"
        function toggle(): void { root.toggle(); }
        function open(): void { root.openPanel(); }
        function close(): void { root.closePanel(); }
    }

    HyprlandFocusGrab {
        id: focusGrab
        windows: [root]
        active: root.isOpen
        onCleared: root.closePanel()
    }

    Item {
        id: keyCatcher
        anchors.fill: parent
        focus: root.isOpen
        Keys.onEscapePressed: root.closePanel()
    }

    Timer {
        id: closeTimer
        interval: 170
        onTriggered: root.visible = false
    }

    Process {
        id: stateProc
        command: ["python3", root.backend, "state"]
        stdout: StdioCollector {
            onStreamFinished: root.readState(this.text)
        }
        onExited: (code) => {
            if (code !== 0) root.busy = false;
        }
    }

    Process {
        id: toggleProc
        command: ["python3", root.backend, "state"]
        stdout: StdioCollector {
            onStreamFinished: root.readState(this.text)
        }
        onExited: (code) => {
            root.busy = false;
        }
    }

    Rectangle {
        id: panel
        anchors.fill: parent
        radius: 0
        color: "#f5100b10"
        border.width: 1
        border.color: "#8a5261"
        opacity: 0
        scale: 0.985
        transformOrigin: Item.Top
        Behavior on opacity { NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }
        Behavior on scale { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }

        Rectangle {
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            height: 2
            color: "#c96a80"
        }

        Item {
            id: content
            anchors.fill: parent
            anchors.margins: 16

            Item {
                id: header
                anchors.top: parent.top
                anchors.left: parent.left
                anchors.right: parent.right
                height: 60

                Column {
                    anchors.left: parent.left
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 3

                    Text {
                        text: "ANYA FORGER DOCUMENTATION ZONE"
                        color: "#d98ca0"
                        font.pixelSize: 9
                        font.weight: Font.DemiBold
                        font.letterSpacing: 1.35
                    }
                    Text {
                        text: root.state.greeting + ", Musi"
                        color: "#f7ebef"
                        font.pixelSize: 19
                        font.weight: Font.DemiBold
                        font.letterSpacing: 0.2
                    }
                    Text {
                        text: root.state.message
                        color: "#b99ca5"
                        font.pixelSize: 11
                    }
                }
            }

            Rectangle {
                id: divider
                anchors.top: header.bottom
                anchors.topMargin: 10
                anchors.left: parent.left
                anchors.right: parent.right
                height: 1
                color: "#3a222a"
            }

            Text {
                id: footer
                anchors.bottom: parent.bottom
                anchors.left: parent.left
                anchors.right: parent.right
                height: 14
                verticalAlignment: Text.AlignVCenter
                text: root.errorText.length > 0
                      ? root.errorText
                      : (root.busy ? "Saving…" : "Click a task to toggle it  ·  Click outside or Esc to close")
                color: root.errorText.length > 0 ? "#ff9cac" : "#8f747c"
                font.pixelSize: 9
                elide: Text.ElideRight
            }

            RowLayout {
                id: body
                anchors.top: divider.bottom
                anchors.topMargin: 12
                anchors.bottom: footer.top
                anchors.bottomMargin: 10
                anchors.left: parent.left
                anchors.right: parent.right
                spacing: 16

                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    spacing: 7

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 6

                        Text {
                            Layout.fillWidth: true
                            text: "HERE IS YOUR TODOS, MY FRIENDO"
                            color: "#e08a9d"
                            font.pixelSize: 10
                            font.weight: Font.DemiBold
                            font.letterSpacing: 1.0
                        }
                        Text {
                            text: root.state.total > 0 ? root.state.remaining + " LEFT" : ""
                            color: "#8f747c"
                            font.pixelSize: 9
                        }
                    }

                    ListView {
                        id: todoList
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        spacing: 4
                        boundsBehavior: Flickable.StopAtBounds
                        model: root.todos
                        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                        delegate: Rectangle {
                            id: todoRow
                            required property var modelData
                            width: todoList.width - 8
                            height: 28
                            radius: 5
                            color: todoMouse.containsMouse ? "#45232c30" : "transparent"
                            Behavior on color { ColorAnimation { duration: 100 } }

                            Rectangle {
                                id: checkBox
                                width: 15
                                height: 15
                                anchors.left: parent.left
                                anchors.leftMargin: 7
                                anchors.verticalCenter: parent.verticalCenter
                                radius: 3
                                color: todoRow.modelData.done ? "#8f3d52" : "transparent"
                                border.width: 1
                                border.color: todoRow.modelData.done ? "#ff9cac" : "#7d5a63"

                                Text {
                                    anchors.centerIn: parent
                                    visible: todoRow.modelData.done
                                    text: "✓"
                                    color: "#fff2f5"
                                    font.pixelSize: 10
                                    font.weight: Font.Bold
                                }
                            }

                            Text {
                                anchors.left: checkBox.right
                                anchors.leftMargin: 9
                                anchors.right: parent.right
                                anchors.rightMargin: 6
                                anchors.verticalCenter: parent.verticalCenter
                                text: todoRow.modelData.text
                                color: todoRow.modelData.done ? "#8b747c" : "#eddfe3"
                                font.pixelSize: 11
                                font.strikeout: todoRow.modelData.done
                                elide: Text.ElideRight
                            }

                            MouseArea {
                                id: todoMouse
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.toggleTodo(todoRow.modelData.index)
                            }
                        }
                    }

                    Text {
                        visible: root.todos.length === 0
                        text: "Nothing here yet — add a line to ~/todo.md"
                        color: "#8f747c"
                        font.pixelSize: 10
                    }
                }

                Rectangle {
                    Layout.preferredWidth: 1
                    Layout.fillHeight: true
                    color: "#2f1c23"
                }

                ColumnLayout {
                    Layout.preferredWidth: 238
                    Layout.fillHeight: true
                    spacing: 5

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 4

                        Text {
                            Layout.fillWidth: true
                            text: "CALENDAR"
                            color: "#e08a9d"
                            font.pixelSize: 10
                            font.weight: Font.DemiBold
                            font.letterSpacing: 1.0
                        }

                        Rectangle {
                            width: 22
                            height: 22
                            radius: 5
                            color: prevArea.containsMouse ? "#45232c30" : "transparent"
                            Behavior on color { ColorAnimation { duration: 100 } }
                            Text {
                                anchors.centerIn: parent
                                text: "‹"
                                color: "#e0c3ca"
                                font.pixelSize: 16
                            }
                            MouseArea {
                                id: prevArea
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.shiftMonth(-1)
                            }
                        }

                        Rectangle {
                            width: 22
                            height: 22
                            radius: 5
                            color: nextArea.containsMouse ? "#45232c30" : "transparent"
                            Behavior on color { ColorAnimation { duration: 100 } }
                            Text {
                                anchors.centerIn: parent
                                text: "›"
                                color: "#e0c3ca"
                                font.pixelSize: 16
                            }
                            MouseArea {
                                id: nextArea
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.shiftMonth(1)
                            }
                        }
                    }

                    Text {
                        Layout.fillWidth: true
                        text: root.monthLabel()
                        color: "#f0dfe4"
                        font.pixelSize: 12
                        font.weight: Font.DemiBold
                        horizontalAlignment: Text.AlignHCenter
                    }

                    DayOfWeekRow {
                        Layout.alignment: Qt.AlignHCenter
                        spacing: 3
                        delegate: Text {
                            required property string shortName
                            width: 29
                            height: 15
                            text: shortName
                            color: "#a98d95"
                            font.pixelSize: 9
                            font.weight: Font.DemiBold
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                        }
                    }

                    MonthGrid {
                        id: monthGrid
                        Layout.alignment: Qt.AlignHCenter
                        Layout.fillHeight: true
                        month: root.viewMonth
                        year: root.viewYear
                        spacing: 3
                        delegate: Rectangle {
                            required property var model
                            implicitWidth: 29
                            implicitHeight: 25
                            radius: 5
                            readonly property bool isToday: model.day === root.state.todayDay
                                                            && model.month === root.state.todayMonth
                                                            && model.year === root.state.todayYear
                            readonly property bool inMonth: model.month === monthGrid.month
                            color: isToday ? "#7d2d40" : "transparent"
                            border.width: isToday ? 1 : 0
                            border.color: "#ff9cac"

                            Text {
                                anchors.centerIn: parent
                                text: model.day
                                color: isToday ? "#fff5f7" : (inMonth ? "#d8c6cc" : "#6d585f")
                                font.pixelSize: 10
                                font.weight: isToday ? Font.DemiBold : Font.Normal
                            }
                        }
                    }

                    Text {
                        Layout.fillWidth: true
                        text: root.state.dateLabel
                        color: "#8f747c"
                        font.pixelSize: 9
                        horizontalAlignment: Text.AlignHCenter
                    }
                }
            }
        }
    }
}

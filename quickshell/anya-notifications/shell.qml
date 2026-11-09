// Anya Forger notification daemon.
// Owns org.freedesktop.Notifications and renders crimson-glass popups.
import Quickshell
import Quickshell.Services.Notifications
import Quickshell.Wayland
import QtQuick

PanelWindow {
    id: root

    anchors {
        top: true
        right: true
    }
    margins {
        top: 42
        right: 12
    }

    implicitWidth: 372
    implicitHeight: column.implicitHeight
    color: "transparent"
    visible: root.items.length > 0
    focusable: false
    exclusiveZone: 0

    WlrLayershell.namespace: "anya-notifications"
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
    WlrLayershell.layer: WlrLayer.Overlay

    property var items: []

    function addNotification(notification) {
        if (!notification)
            return;

        const entry = {
            key: Date.now() + "-" + Math.random(),
            summary: notification.summary || "ANYA // NOTIFICATION",
            body: notification.body || "",
            appName: notification.appName || "Anya Forger"
        };

        root.items = [entry].concat(root.items).slice(0, 3);
    }

    function removeNotification(key) {
        root.items = root.items.filter(item => item.key !== key);
    }

    NotificationServer {
        id: server
        keepOnReload: false
        persistenceSupported: false
        bodySupported: true
        bodyMarkupSupported: false
        bodyHyperlinksSupported: false
        bodyImagesSupported: false
        actionsSupported: false
        actionIconsSupported: false
        imageSupported: true
        inlineReplySupported: false
        onNotification: (notification) => root.addNotification(notification)
    }

    Column {
        id: column
        width: parent.width
        spacing: 8

        Repeater {
            model: root.items

            delegate: Rectangle {
                id: card
                required property var modelData

                width: column.width
                height: Math.max(70, content.implicitHeight + 24)
                color: "#f5100b10"
                border.width: 1
                border.color: "#8a5261"

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
                    anchors.margins: 12
                    implicitHeight: details.implicitHeight

                    Image {
                        id: anya
                        source: "/home/anya/.config/waybar/assets/anya/happy.png"
                        width: 42
                        height: 42
                        fillMode: Image.PreserveAspectFit
                    }

                    Column {
                        id: details
                        anchors.left: anya.right
                        anchors.leftMargin: 10
                        anchors.right: closeButton.left
                        anchors.rightMargin: 10
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 2

                        Text {
                            text: "ANYA FORGER"
                            color: "#d98ca0"
                            font.family: "JetBrains Mono"
                            font.pixelSize: 9
                            font.weight: Font.DemiBold
                        }

                        Text {
                            text: modelData.summary
                            color: "#f7ebef"
                            font.family: "JetBrains Mono"
                            font.pixelSize: 12
                            font.weight: Font.DemiBold
                            wrapMode: Text.Wrap
                            width: parent.width
                        }

                        Text {
                            text: modelData.body
                            color: "#b99ca5"
                            font.family: "JetBrains Mono"
                            font.pixelSize: 10
                            wrapMode: Text.Wrap
                            width: parent.width
                            visible: text !== ""
                        }
                    }

                    Text {
                        id: closeButton
                        anchors.right: parent.right
                        anchors.top: parent.top
                        text: "×"
                        color: "#f0c4ce"
                        font.pixelSize: 15

                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.removeNotification(modelData.key)
                        }
                    }
                }

                Timer {
                    interval: 8000
                    running: true
                    onTriggered: root.removeNotification(modelData.key)
                }
            }
        }
    }
}

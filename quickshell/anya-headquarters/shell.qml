pragma ComponentBehavior: Bound

import Quickshell
import Quickshell.Hyprland
import Quickshell.Io
import Quickshell.Wayland
import QtQuick
import QtQuick.Controls

PanelWindow {
    id: root

    anchors { top: true; right: true }
    margins { top: 8; right: 10 }
    implicitWidth: 416
    implicitHeight: 654
    color: "transparent"
    visible: false
    focusable: true
    WlrLayershell.namespace: "crimson-quicksettings"
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.OnDemand

    property bool isOpen: false
    property bool scanning: false
    property bool scanningBt: false
    property string busyDevice: ""
    property bool refreshQueued: false
    property string section: "Control"
    property string statusMessage: ""
    property bool errorState: false
    property bool confirmWifiOff: false
    property bool statusReady: false
    property var systemState: ({})
    property var networks: []
    property var devices: []
    property var sinks: []
    property var sources: []
    property var pendingNetwork: null
    property string pendingPassword: ""
    property string networkFilter: ""
    property real volume: 0
    property real inputVolume: 0
    property real brightness: 0
    property string clockText: ""
    property var actionQueue: []
    property var pendingTweaks: ({})

    readonly property string backend: "/home/anya/.config/waybar/control-center.py"

    function refresh() {
        if (statusProc.running) {
            // A status query is already in flight (often the one started before
            // an action finished). Re-run afterwards instead of dropping the
            // request, otherwise the panel can show stale Bluetooth state.
            refreshQueued = true;
            return;
        }
        refreshQueued = false;
        if (!statusReady) {
            statusMessage = "Loading device status…";
            errorState = false;
        }
        statusProc.running = true;
    }
    function invoke(name, args) {
        actionQueue.push({ name: name, args: args || [] });
        if (!actionProc.running) Qt.callLater(root.startNextAction);
    }
    function startNextAction() {
        if (actionProc.running || actionQueue.length === 0) return;
        const next = actionQueue.shift();
        actionProc.command = ["python3", root.backend, next.name].concat(next.args);
        actionProc.running = true;
    }
    function tweak(name, args) {
        pendingTweaks[name] = args;
        if (!tweakProc.running) Qt.callLater(root.startNextTweak);
    }
    function startNextTweak() {
        if (tweakProc.running) return;
        const names = Object.keys(pendingTweaks);
        if (names.length === 0) return;
        const name = names[0];
        const args = pendingTweaks[name];
        delete pendingTweaks[name];
        if (name === "volume") {
            tweakProc.command = ["wpctl", "set-volume", "-l", "1", "@DEFAULT_AUDIO_SINK@", args[0]];
        } else if (name === "input-volume") {
            tweakProc.command = ["wpctl", "set-volume", "-l", "1", "@DEFAULT_AUDIO_SOURCE@", args[0]];
        } else if (name === "brightness") {
            tweakProc.command = ["brightnessctl", "set", Math.max(1, Math.round(args[0] * 100)) + "%"];
        } else {
            tweakProc.command = ["python3", root.backend, name].concat(args);
        }
        tweakProc.running = true;
    }
    function startWifiScan() {
        if (scanWifiProc.running) return;
        scanning = true;
        scanWifiProc.command = ["python3", root.backend, "wifi-scan"];
        scanWifiProc.running = true;
    }
    function startBluetoothScan() {
        if (scanBtProc.running) return;
        scanningBt = true;
        statusMessage = "Scanning for Bluetooth devices…";
        errorState = false;
        scanBtProc.running = true;
    }
    function bluetoothAction(device) {
        if (!device || busyDevice.length > 0) return;
        busyDevice = device.address;
        statusMessage = device.connected
            ? "Disconnecting " + device.name + "…"
            : (device.paired ? "Connecting to " + device.name + "…" : "Pairing with " + device.name + "…");
        errorState = false;
        invoke(device.connected ? "bt-disconnect" : (device.paired ? "bt-connect" : "bt-pair"),
               [device.address, device.name]);
    }
    function openPanel() {
        if (!isOpen) toggle();
        else refresh();
    }
    Component.onCompleted: root.refresh()
    function readStatus(raw) {
        try {
            const response = JSON.parse(raw);
            if (!response.ok) throw new Error(response.error || "Could not read system status");
            const state = response.status;
            systemState = state;
            statusReady = true;
            if (Array.isArray(state.wifiNetworks)) networks = state.wifiNetworks;
            devices = state.bluetoothDevices || [];
            sinks = state.sinks || [];
            sources = state.sources || [];
            volume = state.volume || 0;
            inputVolume = state.inputVolume || 0;
            brightness = state.brightness || 0;
            if (!controlVolume.pressed) controlVolume.value = volume;
            if (!audioVolume.pressed) audioVolume.value = volume;
            if (!audioInput.pressed) audioInput.value = inputVolume;
            if (!displayBrightness.pressed) displayBrightness.value = brightness;
            if (root.isOpen && state.wifiEnabled && networks.length === 0 && !scanWifiProc.running)
                root.startWifiScan();
            if (statusMessage === "System status query failed" || statusMessage === "Loading device status…") {
                statusMessage = "";
                errorState = false;
            }
        } catch (error) {
            statusMessage = String(error);
            errorState = true;
        }
    }
    function readAction(raw, exitCode) {
        try {
            const response = JSON.parse(raw);
            if (!response.ok || (exitCode !== undefined && exitCode !== 0)) throw new Error(response.error || "The action did not complete");
            statusMessage = response.networks
                ? (response.networks.length ? "Found " + response.networks.length + " Wi-Fi networks" : "No Wi-Fi networks found")
                : (response.message || "Updated");
            errorState = false;
            if (response.networks) networks = response.networks;
        } catch (error) {
            statusMessage = String(error).replace(/^Error: /, "");
            errorState = true;
        }
        refreshTimer.restart();
        settleTimer.restart();
        messageTimer.restart();
    }
    function toggle() {
        isOpen = !isOpen;
        if (isOpen) {
            closeTimer.stop();
            visible = true;
            clockText = Qt.formatDateTime(new Date(), "ddd · d MMM  HH:mm");
            refresh();
            refreshTimer.restart();
            Qt.callLater(function() { panel.opacity = 1; panel.scale = 1; keyCatcher.forceActiveFocus(); });
        } else {
            panel.opacity = 0;
            panel.scale = 0.985;
            closeTimer.restart();
        }
    }
    function closePanel() {
        if (isOpen) {
            isOpen = false;
            panel.opacity = 0;
            panel.scale = 0.985;
            closeTimer.restart();
        }
    }
    function confirmWifiToggle() {
        if (systemState.wifiConnected && !confirmWifiOff) {
            confirmWifiOff = true;
            statusMessage = "Wi-Fi is connected. Press the Wi-Fi tile again to confirm disconnecting it.";
            errorState = true;
            messageTimer.restart();
        } else {
            confirmWifiOff = false;
            invoke("wifi-toggle", []);
        }
    }

    IpcHandler {
        target: "anya"
        function toggle(): void { root.toggle(); }
        function openPanel(): void { root.openPanel(); }
        function close(): void { root.closePanel(); }
    }

    // Clicking anywhere outside the panel dismisses it. The focus grab also
    // keeps keyboard focus while the panel is open.
    HyprlandFocusGrab {
        id: focusGrab
        windows: [root]
        active: root.isOpen
        onCleared: root.closePanel()
    }

    Process {
        id: statusProc
        command: ["python3", "/home/anya/.config/waybar/control-center.py", "status"]
        stdout: StdioCollector { onStreamFinished: root.readStatus(this.text) }
        onExited: (code) => {
            if (code !== 0 && root.statusMessage === "Loading device status…") { root.statusMessage = "System status query failed"; root.errorState = true; }
            if (root.refreshQueued) { root.refreshQueued = false; root.refresh(); }
        }
    }
    Process {
        id: scanWifiProc
        command: ["python3", "/home/anya/.config/waybar/control-center.py", "wifi-scan"]
        stdout: StdioCollector { id: scanOut }
        stderr: StdioCollector { id: scanOutErr }
        onExited: (code) => {
            root.scanning = false;
            if (code === 0 && scanOut.text.trim()) {
                root.readAction(scanOut.text, code);
            } else {
                const message = (scanOutErr.text.trim() || "Wi-Fi scan failed").replace(/[\r\n]+/g, " ").replace(/["\\]/g, "'");
                root.readAction('{"ok":false,"error":"' + message + '"}', 1);
            }
        }
    }
    Process {
        id: scanBtProc
        command: ["python3", root.backend, "bt-scan"]
        stdout: StdioCollector { id: scanBtOut }
        stderr: StdioCollector { id: scanBtErr }
        onExited: (code) => {
            root.scanningBt = false;
            if (code === 0 && scanBtOut.text.trim()) {
                root.readAction(scanBtOut.text, code);
            } else {
                const message = (scanBtErr.text.trim() || "Bluetooth scan failed").replace(/[\r\n]+/g, " ").replace(/["\\]/g, "'");
                root.readAction('{"ok":false,"error":"' + message + '"}', 1);
            }
        }
    }
    Process {
        id: actionProc
        stdout: StdioCollector { id: actionOut }
        stderr: StdioCollector { id: actionErr }
        onExited: (code) => {
            const raw = actionOut.text.trim() ? actionOut.text : actionErr.text;
            if (raw.trim().length) root.readAction(raw, code);
            else if (code !== 0) root.readAction('{"ok":false,"error":"The action did not complete"}', 1);
            Qt.callLater(root.startNextAction);
            // Keep "Working…" until the queue drains so a queued Bluetooth
            // action still shows as in progress.
            if (root.actionQueue.length === 0) root.busyDevice = "";
        }
    }
    Process {
        id: tweakProc
        stdout: StdioCollector {}
        stderr: StdioCollector {}
        onExited: (code) => Qt.callLater(root.startNextTweak)
    }

    Timer { id: refreshTimer; interval: 400; onTriggered: root.refresh() }
    Timer { id: settleTimer; interval: 1800; onTriggered: root.refresh() }
    Timer { id: pollTimer; interval: 15000; repeat: true; running: root.isOpen; onTriggered: root.refresh() }
    Timer { id: closeTimer; interval: 170; onTriggered: root.visible = false }
    Timer { id: messageTimer; interval: 6500; onTriggered: { root.statusMessage = ""; root.errorState = false; root.confirmWifiOff = false; } }
    Timer { id: clockTimer; interval: 1000; running: root.isOpen; repeat: true; onTriggered: root.clockText = Qt.formatDateTime(new Date(), "ddd · d MMM  HH:mm") }

    Item {
        id: keyCatcher
        anchors.fill: parent
        focus: root.isOpen
        Keys.onEscapePressed: root.closePanel()
    }

    Rectangle {
        id: panel
        anchors.fill: parent
        radius: 22
        color: "#ed100b10"
        border.color: "#687b3545"
        border.width: 1
        opacity: 0
        scale: 0.985
        transformOrigin: Item.TopRight
        Behavior on opacity { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } }
        Behavior on scale { NumberAnimation { duration: 175; easing.type: Easing.OutCubic } }

        Column {
            anchors.fill: parent
            anchors.margins: 15
            spacing: 10

            Row {
                width: parent.width
                height: 48
                spacing: 8
                Column {
                    width: parent.width
                    spacing: 2
                    Text { text: "Anya's system control"; color: "#f0e5e8"; font.pixelSize: 15; font.weight: Font.DemiBold; font.letterSpacing: 1.1 }
                    Text { text: root.clockText + "   ·   " + (root.systemState.battery || "Power status unavailable"); color: "#b99ca5"; font.pixelSize: 10 }
                }
            }

            Row {
                width: parent.width
                spacing: 5
                Repeater {
                    model: ["Control", "Audio", "Display", "System"]
                    delegate: GlassButton {
                        required property string modelData
                        width: (parent.width - 15) / 4
                        height: 31
                        label: modelData
                        selected: root.section === modelData
                        onClicked: root.section = modelData
                    }
                }
            }

            Rectangle {
                visible: root.statusMessage.length > 0
                width: parent.width
                height: visible ? 34 : 0
                radius: 9
                color: root.errorState ? "#55311b25" : "#40231920"
                border.color: root.errorState ? "#9e5664" : "#70533844"
                Text { anchors.fill: parent; anchors.margins: 8; text: root.statusMessage; color: root.errorState ? "#ffc4ce" : "#e0cbd0"; font.pixelSize: 10; elide: Text.ElideRight; verticalAlignment: Text.AlignVCenter }
            }

            ScrollView {
                id: bodyScroll
                width: parent.width
                height: parent.height - (root.statusMessage.length > 0 ? 152 : 118)
                enabled: root.statusReady
                clip: true
                ScrollBar.vertical.policy: ScrollBar.AsNeeded

                Column {
                    width: bodyScroll.width
                    spacing: 10
                    visible: root.section === "Control"
                    height: visible ? implicitHeight : 0

                    Text { text: "CONNECTIVITY"; color: "#b88794"; font.pixelSize: 9; font.weight: Font.DemiBold; font.letterSpacing: 1.0 }

                    Row {
                        width: parent.width; spacing: 8
                        StatusTile {
                            width: (parent.width - 8) / 2
                            title: "Wi-Fi"
                            detail: !root.systemState.wifiEnabled ? "Off" : (root.systemState.wifiConnected ? root.systemState.wifiConnection : "Available")
                            symbol: "⌁"
                            active: !!root.systemState.wifiEnabled
                            onClicked: root.confirmWifiToggle()
                        }
                        StatusTile {
                            width: (parent.width - 8) / 2
                            title: "Bluetooth"
                            detail: !root.systemState.bluetoothEnabled ? "Off" : (root.devices.some(function(d) { return d.connected; }) ? "Connected" : "On")
                            symbol: "ᛒ"
                            active: !!root.systemState.bluetoothEnabled
                            onClicked: root.invoke("bluetooth-toggle", [])
                        }
                    }

                    Row {
                        width: parent.width; spacing: 7
                        GlassButton { width: (parent.width - 14) / 3; label: root.scanning ? "Scanning…" : "Scan Wi-Fi"; enabled: !root.scanning; onClicked: root.startWifiScan() }
                        GlassButton { width: (parent.width - 14) / 3; label: root.scanningBt ? "Scanning…" : "Scan Bluetooth"; enabled: !root.scanningBt; onClicked: root.startBluetoothScan() }
                        GlassButton { width: (parent.width - 14) / 3; label: root.systemState.wifiConnected ? "Disconnect" : "Network settings"; onClicked: root.systemState.wifiConnected ? root.invoke("wifi-disconnect", []) : root.invoke("open-network-settings", []) }
                    }

                    Text { text: "BLUETOOTH DEVICES"; color: "#b88794"; font.pixelSize: 9; font.weight: Font.DemiBold; font.letterSpacing: 1.0; topPadding: 3 }
                    Repeater {
                        model: root.devices
                        delegate: Rectangle {
                            required property var modelData
                            width: parent.width; height: 40; radius: 9
                            color: modelData.connected ? "#563c1e2a" : (deviceClick.containsMouse ? "#43251a22" : "#321a1419")
                            border.color: modelData.connected ? "#864656" : "#42393137"
                            MouseArea {
                                id: deviceClick
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.bluetoothAction(modelData)
                            }
                            Row {
                                anchors.fill: parent; anchors.margins: 7; spacing: 5
                                Text { width: parent.width - deviceAction.width - parent.spacing; text: modelData.name + (modelData.connected ? " · Connected" : (modelData.paired ? " · Paired" : "")); color: "#ebdce0"; font.pixelSize: 10; elide: Text.ElideRight; anchors.verticalCenter: parent.verticalCenter }
                                GlassButton {
                                    id: deviceAction
                                    width: 84; height: 27; anchors.verticalCenter: parent.verticalCenter
                                    label: root.busyDevice === modelData.address ? "Working…" : (modelData.connected ? "Disconnect" : (modelData.paired ? "Connect" : "Pair"))
                                    hint: modelData.name + " · " + (modelData.connected ? "Connected" : (modelData.paired ? "Paired" : "Not paired"))
                                    enabled: root.busyDevice.length === 0 || root.busyDevice === modelData.address
                                    onClicked: root.bluetoothAction(modelData)
                                }
                            }
                        }
                    }
                    Text { visible: !!root.systemState.bluetoothEnabled && root.devices.length === 0; text: "No known devices yet. Scan to discover devices in pairing mode."; color: "#a99299"; font.pixelSize: 9; wrapMode: Text.WordWrap }

                    Text { text: "WI-FI NETWORKS"; color: "#b88794"; font.pixelSize: 9; font.weight: Font.DemiBold; font.letterSpacing: 1.0; topPadding: 3 }
                    TextField {
                        width: parent.width
                        height: 32
                        placeholderText: "Filter Wi-Fi names · " + root.networks.length + " found"
                        text: root.networkFilter
                        onTextChanged: root.networkFilter = text
                        selectByMouse: true
                        color: "#f0e5e8"
                        font.pixelSize: 10
                        leftPadding: 10
                        background: Rectangle { color: "#30150d12"; radius: 8; border.color: "#59424a53" }
                    }

                    Repeater {
                        model: root.networks.filter(function(network) {
                            return !root.networkFilter || network.ssid.toLowerCase().indexOf(root.networkFilter.toLowerCase()) >= 0;
                        }).slice(0, root.networkFilter ? 100 : 8)
                        delegate: Rectangle {
                            required property var modelData
                            width: parent.width
                            height: 47
                            radius: 10
                            color: modelData.inUse ? "#603c1e2a" : "#4220161d"
                            border.color: modelData.inUse ? "#8b4d5d" : "#4c493038"
                            Row {
                                anchors.fill: parent; anchors.leftMargin: 10; anchors.rightMargin: 8; spacing: 6
                                Column {
                                    width: parent.width - connectButton.width - parent.spacing - 18
                                    anchors.verticalCenter: parent.verticalCenter
                                    Text { width: parent.width; text: modelData.ssid; color: "#f0e3e7"; font.pixelSize: 11; elide: Text.ElideRight }
                                    Text { width: parent.width; text: modelData.security + "   ·   " + modelData.signal + "%"; color: "#aa9299"; font.pixelSize: 9; elide: Text.ElideRight }
                                }
                                GlassButton {
                                    id: connectButton
                                    width: 84; height: 29
                                    anchors.verticalCenter: parent.verticalCenter
                                    label: modelData.inUse ? "Connected" : (modelData.security.toUpperCase().indexOf("802.1X") >= 0 || modelData.security.toUpperCase().indexOf("WPA-EAP") >= 0 ? "Set up" : "Connect")
                                    hint: modelData.security.toUpperCase().indexOf("802.1X") >= 0 || modelData.security.toUpperCase().indexOf("WPA-EAP") >= 0 ? "Configure EAP, then click Set up again to connect" : "Connect to " + modelData.ssid
                                    selected: modelData.inUse
                                    onClicked: {
                                        if (modelData.inUse) return;
                                        if (modelData.security.toUpperCase().indexOf("802.1X") >= 0 || modelData.security.toUpperCase().indexOf("WPA-EAP") >= 0) root.invoke("wifi-setup", [modelData.ssid]);
                                        else if (modelData.security !== "Open") { root.pendingNetwork = modelData; wifiPasswordField.clear(); root.pendingPassword = ""; }
                                        else root.invoke("wifi-connect", [modelData.ssid, modelData.security, ""]);
                                    }
                                }
                            }
                        }
                    }

                    Rectangle {
                        visible: root.pendingNetwork !== null
                        width: parent.width; height: visible ? 76 : 0
                        radius: 11; color: "#54291a24"; border.color: "#7d4555"
                        Row {
                            anchors.fill: parent; anchors.margins: 8; spacing: 6
                            TextField {
                                id: wifiPasswordField
                                width: parent.width - wifiConnect.width - 6
                                height: 36
                                anchors.verticalCenter: parent.verticalCenter
                                placeholderText: "Password for " + (root.pendingNetwork ? root.pendingNetwork.ssid : "network")
                                echoMode: TextInput.Password
                                onTextChanged: root.pendingPassword = text
                                color: "#f0e5e8"
                                background: Rectangle { color: "#30150d12"; radius: 8; border.color: "#75455360" }
                            }
                            GlassButton {
                                id: wifiConnect
                                width: 84; height: 36; anchors.verticalCenter: parent.verticalCenter
                                label: "Connect"
                                onClicked: {
                                    if (root.pendingNetwork) root.invoke("wifi-connect", [root.pendingNetwork.ssid, root.pendingNetwork.security, root.pendingPassword]);
                                    root.pendingNetwork = null; wifiPasswordField.clear(); root.pendingPassword = "";
                                }
                            }
                        }
                    }

                    Rectangle {
                        width: parent.width; height: 42; radius: 10
                        color: root.systemState.hotspotActive ? "#633d1e2a" : "#3820181d"
                        border.color: root.systemState.hotspotActive ? "#9a5060" : "#4e493038"
                        Row {
                            anchors.fill: parent; anchors.leftMargin: 11; anchors.rightMargin: 8; spacing: 6
                            Text { width: parent.width - hotspotButton.width - parent.spacing; text: root.systemState.hotspotActive ? "Hotspot · on" : (root.systemState.hotspotAvailable ? "Mobile hotspot · off" : "Hotspot unavailable"); color: "#e9d8dc"; font.pixelSize: 10; anchors.verticalCenter: parent.verticalCenter; elide: Text.ElideRight }
                            GlassButton { id: hotspotButton; width: 84; height: 28; anchors.verticalCenter: parent.verticalCenter; label: root.systemState.hotspotAvailable ? (root.systemState.hotspotActive ? "Turn off" : "Turn on") : "Details"; enabled: !!root.systemState.hotspotAvailable; onClicked: root.invoke("hotspot-toggle", []) }
                        }
                    }
                    Text { visible: !root.systemState.hotspotAvailable; width: parent.width; text: root.systemState.hotspotReason || "AP capability or sharing helper unavailable"; color: "#b8979f"; font.pixelSize: 9; wrapMode: Text.WordWrap }

                    Text { text: "AUDIO"; color: "#b88794"; font.pixelSize: 9; font.weight: Font.DemiBold; font.letterSpacing: 1.0; topPadding: 3 }
                    Row {
                        width: parent.width; spacing: 8
                        Text { text: "Output"; color: "#e8d7dc"; font.pixelSize: 10; anchors.verticalCenter: parent.verticalCenter }
                        GlassButton { width: 112; label: root.systemState.muted ? "Muted" : Math.round(root.volume * 100) + "%"; selected: !!root.systemState.muted; onClicked: root.invoke("mute", []) }
                        GlassSlider { id: controlVolume; width: parent.width - 176; from: 0; to: 1; hoverHint: "Master output · " + Math.round(root.volume * 100) + "%"; anchors.verticalCenter: parent.verticalCenter; onMoved: { root.volume = value; if (!audioVolume.pressed) audioVolume.value = value; root.tweak("volume", [value.toFixed(2)]); } }
                    }
                    Repeater {
                        model: root.sinks
                        delegate: GlassButton { required property var modelData; width: parent.width; height: 32; label: (modelData.name === root.systemState.defaultSink ? "●  " : "○  ") + modelData.description; hint: modelData.description + " · " + (modelData.name === root.systemState.defaultSink ? "Current output" : "Click to route audio here"); selected: modelData.name === root.systemState.defaultSink; onClicked: root.invoke("audio-sink", [modelData.name]) }
                    }
                }

                Column {
                    width: bodyScroll.width; spacing: 12; visible: root.section === "Audio"; height: visible ? implicitHeight : 0
                    Text { text: "OUTPUT ROUTING"; color: "#b88794"; font.pixelSize: 9; font.weight: Font.DemiBold; font.letterSpacing: 1 }
                    Row { width: parent.width; spacing: 8
                        GlassButton { width: 75; label: root.systemState.muted ? "Unmute" : "Mute"; selected: !!root.systemState.muted; onClicked: root.invoke("mute", []) }
                        GlassSlider { id: audioVolume; width: parent.width - 140; from: 0; to: 1; hoverHint: "Master output · " + Math.round(root.volume * 100) + "%"; anchors.verticalCenter: parent.verticalCenter; onMoved: { root.volume = value; if (!controlVolume.pressed) controlVolume.value = value; root.tweak("volume", [value.toFixed(2)]); } }
                        Text { width: 48; text: Math.round(root.volume * 100) + "%"; color: "#d8c2c8"; anchors.verticalCenter: parent.verticalCenter; font.pixelSize: 10 }
                    }
                    Repeater { model: root.sinks; delegate: GlassButton { required property var modelData; width: parent.width; height: 36; label: (modelData.name === root.systemState.defaultSink ? "●  " : "○  ") + modelData.description; hint: modelData.description + "\n" + modelData.name + "\n" + (modelData.name === root.systemState.defaultSink ? "Current output" : "Click to route audio here"); selected: modelData.name === root.systemState.defaultSink; onClicked: root.invoke("audio-sink", [modelData.name]) } }
                    Text { text: "INPUT ROUTING"; color: "#b88794"; font.pixelSize: 9; font.weight: Font.DemiBold; font.letterSpacing: 1; topPadding: 4 }
                    Row { width: parent.width; spacing: 8
                        GlassButton { width: 75; label: root.systemState.inputMuted ? "Mic on" : "Mic mute"; selected: !!root.systemState.inputMuted; onClicked: root.invoke("input-mute", []) }
                        GlassSlider { id: audioInput; width: parent.width - 140; from: 0; to: 1; hoverHint: "Microphone input · " + Math.round(root.inputVolume * 100) + "%"; anchors.verticalCenter: parent.verticalCenter; onMoved: { root.inputVolume = value; root.tweak("input-volume", [value.toFixed(2)]); } }
                        Text { width: 48; text: Math.round(root.inputVolume * 100) + "%"; color: "#d8c2c8"; anchors.verticalCenter: parent.verticalCenter; font.pixelSize: 10 }
                    }
                    Repeater { model: root.sources; delegate: GlassButton { required property var modelData; width: parent.width; height: 36; label: (modelData.name === root.systemState.defaultSource ? "●  " : "○  ") + modelData.description; hint: modelData.description + "\n" + modelData.name + "\n" + (modelData.name === root.systemState.defaultSource ? "Current input" : "Click to use this input"); selected: modelData.name === root.systemState.defaultSource; onClicked: root.invoke("audio-source", [modelData.name]) } }
                    GlassButton { visible: !!root.systemState.audioMixerAvailable; width: parent.width; label: "Open full audio mixer"; onClicked: root.invoke("open-audio-settings", []) }
                    Text { text: "A2DP stereo appears here only while a compatible Bluetooth device is connected."; color: "#a99299"; font.pixelSize: 9; wrapMode: Text.WordWrap }
                }

                Column {
                    width: bodyScroll.width; spacing: 12; visible: root.section === "Display"; height: visible ? implicitHeight : 0
                    Text { text: "DISPLAY"; color: "#b88794"; font.pixelSize: 9; font.weight: Font.DemiBold; font.letterSpacing: 1 }
                    Rectangle {
                        width: parent.width; height: 78; radius: 12; color: "#381b141a"; border.color: "#53402d36"
                        Column { anchors.fill: parent; anchors.margins: 11; spacing: 6
                            Row { width: parent.width; Text { text: "Brightness"; color: "#eadbe0"; font.pixelSize: 11 } Item { width: parent.width - 90; height: 1 } Text { text: root.systemState.brightnessAvailable ? Math.round(root.brightness * 100) + "%" : "Unavailable"; color: "#c39ba6"; font.pixelSize: 10 } }
                            GlassSlider { id: displayBrightness; width: parent.width; from: 0.01; to: 1; hoverHint: "Display brightness · " + Math.round(root.brightness * 100) + "%"; enabled: !!root.systemState.brightnessAvailable; onMoved: { root.brightness = value; root.tweak("brightness", [value.toFixed(2)]); } }
                        }
                    }
                    SectionCard { width: parent.width; heading: "NIGHT LIGHT"; detail: "Unavailable · no compatible night-light utility is installed." }
                    SectionCard { width: parent.width; heading: "SCALING"; detail: "Laptop: 1920×1080 at 1.25 scale · External: 1920×1080 at 1.0." }
                }

                Column {
                    width: bodyScroll.width; spacing: 11; visible: root.section === "System"; height: visible ? implicitHeight : 0
                    Text { text: "SYSTEM"; color: "#b88794"; font.pixelSize: 9; font.weight: Font.DemiBold; font.letterSpacing: 1 }
                    SectionCard { width: parent.width; heading: "POWER"; detail: root.systemState.battery || "Battery status unavailable" }
                    SectionCard { width: parent.width; heading: "THEME"; detail: "GTK dark theme is " + (root.systemState.darkTheme ? "enabled" : "disabled") }
                    GlassButton { width: parent.width; label: "Toggle GTK dark theme"; onClicked: root.invoke("dark-theme", []) }
                    SectionCard { width: parent.width; heading: "DO NOT DISTURB"; detail: root.systemState.notificationBackend ? "Notification backend detected; DND control not yet exposed by that backend." : "Unavailable · no notification daemon is installed." }
                    Row { width: parent.width; spacing: 8
                        GlassButton { width: (parent.width - 8) / 2; label: "Network settings"; onClicked: root.invoke("open-network-settings", []) }
                        GlassButton { visible: !!root.systemState.lockAvailable; width: (parent.width - 8) / 2; label: "Lock screen"; onClicked: root.invoke("lock", []) }
                    }
                    Text { text: "Click outside or press Esc to close. Wi-Fi and Bluetooth controls talk to iwd/NetworkManager and BlueZ."; color: "#98838a"; font.pixelSize: 9; wrapMode: Text.WordWrap }
                }
            }
        }
    }

    component GlassButton: Button {
        id: control
        property alias label: control.text
        property bool selected: false
        property string hint: ""
        implicitHeight: 31
        padding: 5
        hoverEnabled: true
        ToolTip.visible: control.hovered && control.hint.length > 0
        ToolTip.text: control.hint
        ToolTip.delay: 350
        background: Rectangle {
            radius: 9
            color: !control.enabled ? "#251c1a1d" : (control.selected ? "#633d202b" : (control.hovered ? "#55351e28" : "#3e21171f"))
            border.width: 1
            border.color: !control.enabled ? "#34303438" : (control.selected ? "#9a5263" : (control.hovered ? "#77505a" : "#51404a"))
            Behavior on color { ColorAnimation { duration: 110 } }
        }
        contentItem: Text {
            text: control.text
            color: !control.enabled ? "#766b70" : (control.selected ? "#fff0f3" : "#dfcbd1")
            font.pixelSize: 10
            font.weight: control.selected ? Font.DemiBold : Font.Normal
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
    }

    component StatusTile: Button {
        id: control
        property string title: ""
        property string detail: ""
        property string symbol: ""
        property bool active: false
        implicitHeight: 65
        hoverEnabled: true
        background: Rectangle {
            radius: 13
            color: control.active ? "#68402a35" : (control.hovered ? "#50301c26" : "#3c21171e")
            border.width: 1
            border.color: control.active ? "#9c5264" : "#51414a"
            Behavior on color { ColorAnimation { duration: 125 } }
        }
        contentItem: Row {
            spacing: 9
            anchors.leftMargin: 10
            Text { text: control.symbol; color: "#f0a0b0"; font.pixelSize: 17; anchors.verticalCenter: parent.verticalCenter }
            Column {
                anchors.verticalCenter: parent.verticalCenter
                Text { text: control.title; color: "#f1e3e7"; font.pixelSize: 11; font.weight: Font.DemiBold }
                Text { width: 120; text: control.detail; color: "#ba9ca5"; font.pixelSize: 9; elide: Text.ElideRight }
            }
        }
    }

    component SectionCard: Rectangle {
        required property string heading
        required property string detail
        implicitHeight: cardText.implicitHeight + 22
        radius: 11; color: "#371c151b"; border.color: "#493a3037"
        Column { id: cardText; anchors.fill: parent; anchors.margins: 10; spacing: 4
            Text { text: parent.parent.heading; color: "#e8d7dc"; font.pixelSize: 10; font.weight: Font.DemiBold }
            Text { width: parent.width; text: parent.parent.detail; color: "#ae969e"; font.pixelSize: 9; wrapMode: Text.WordWrap }
        }
    }

    component GlassSlider: Slider {
        id: control
        property string hoverHint: ""
        implicitHeight: 24
        hoverEnabled: true
        ToolTip.visible: control.hovered && control.hoverHint.length > 0
        ToolTip.text: control.hoverHint
        ToolTip.delay: 350
        background: Rectangle {
            x: control.leftPadding
            y: control.topPadding + control.availableHeight / 2 - height / 2
            width: control.availableWidth
            height: 4
            radius: 2
            color: "#4b303239"
            Rectangle { width: control.visualPosition * parent.width; height: parent.height; radius: parent.radius; color: control.enabled ? "#9e4b61" : "#66535a" }
        }
        handle: Rectangle {
            x: control.leftPadding + control.visualPosition * (control.availableWidth - width)
            y: control.topPadding + control.availableHeight / 2 - height / 2
            implicitWidth: 13
            implicitHeight: 13
            radius: width / 2
            color: control.pressed ? "#ffd2da" : "#e793a5"
            border.width: 1
            border.color: "#652c3b"
        }
    }
}

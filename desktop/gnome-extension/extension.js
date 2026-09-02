import GObject from 'gi://GObject';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import St from 'gi://St';
import Clutter from 'gi://Clutter';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as QuickSettings from 'resource:///org/gnome/shell/ui/quickSettings.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import {Extension, gettext as _} from 'resource:///org/gnome/shell/extensions/extension.js';

const DBUS_NAME = 'org.connecttophone.Daemon';
const DBUS_PATH = '/org/connecttophone/Daemon';
const DBUS_INTERFACE = 'org.connecttophone.Daemon';

const ConnectToPhoneToggle = GObject.registerClass(
class ConnectToPhoneToggle extends QuickSettings.QuickMenuToggle {
    _init(extension) {
        super._init({
            title: 'Celular',
            subtitle: 'Desativado',
            iconName: 'phone-symbolic',
            toggleMode: true,
        });

        this._extension = extension;
        this.checked = false;
        this.menu.setHeader('phone-symbolic', 'ConnectToPhone', 'Aguardando celular...');

        this._buildMenu();

        // Main button toggle click
        this.connect('clicked', () => {
            this._onMainToggleClicked();
        });

        // Auto-refresh when menu opens
        this.menu.connect('open-state-changed', (menu, isOpen) => {
            if (isOpen) {
                this._extension.fetchStatus();
            }
        });
    }

    _buildMenu() {
        // 1. Device Info & Battery Section
        this._statusSection = new PopupMenu.PopupMenuSection();
        
        this._deviceInfoItem = new PopupMenu.PopupMenuItem('Nenhum aparelho conectado', { reactive: false });
        this._statusSection.addMenuItem(this._deviceInfoItem);

        this._batteryItem = new PopupMenu.PopupImageMenuItem('Bateria: --%', 'battery-level-100-symbolic', { reactive: false });
        this._statusSection.addMenuItem(this._batteryItem);

        this.menu.addMenuItem(this._statusSection);
        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        // 2. Actions Section
        this._openAppItem = new PopupMenu.PopupImageMenuItem('Abrir ConnectToPhone', 'view-paged-symbolic');
        this._openAppItem.connect('activate', () => {
            this._extension.callDaemonMethod('OpenWindow');
        });
        this.menu.addMenuItem(this._openAppItem);

        this._mirrorItem = new PopupMenu.PopupImageMenuItem('Espelhar Tela', 'video-display-symbolic');
        this._mirrorItem.connect('activate', () => {
            this._extension.callDaemonMethod('OpenMirror');
        });
        this.menu.addMenuItem(this._mirrorItem);

        this._pairItem = new PopupMenu.PopupImageMenuItem('Conectar Novo Celular (QR)', 'view-refresh-symbolic');
        this._pairItem.connect('activate', () => {
            this._extension.callDaemonMethod('OpenPairDialog');
        });
        this.menu.addMenuItem(this._pairItem);

        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        // 3. Clipboard Switch
        this._clipSwitchItem = new PopupMenu.PopupSwitchMenuItem('Sincronizar Clipboard', true);
        this._clipSwitchItem.connect('toggled', (item, state) => {
            this._extension.callDaemonMethod('ToggleClipboardSync', new GLib.Variant('(b)', [state]));
        });
        this.menu.addMenuItem(this._clipSwitchItem);

        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        // 4. Reconnect Button
        this._reconnectItem = new PopupMenu.PopupImageMenuItem('Buscar Celular na Rede', 'network-wireless-signal-good-symbolic');
        this._reconnectItem.connect('activate', () => {
            this._extension.callDaemonMethod('ReconnectDevice');
        });
        this.menu.addMenuItem(this._reconnectItem);

        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        // 5. Daemon Toggle Item
        this._daemonToggleItem = new PopupMenu.PopupImageMenuItem('Encerrar Serviço em 2º Plano', 'process-stop-symbolic');
        this._daemonToggleItem.connect('activate', () => {
            this._extension.stopDaemon();
        });
        this.menu.addMenuItem(this._daemonToggleItem);
    }

    _onMainToggleClicked() {
        if (!this._extension.isDaemonRunning()) {
            this.checked = false;
            this.title = 'ConnectToPhone';
            this.subtitle = 'Iniciando em 2º plano...';
            this._extension.startDaemon();

            let attempts = 0;
            const pollId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 300, () => {
                attempts++;
                if (this._extension.isDaemonRunning()) {
                    this._extension.fetchStatus();
                    return GLib.SOURCE_REMOVE;
                }
                if (attempts >= 10) {
                    return GLib.SOURCE_REMOVE;
                }
                return GLib.SOURCE_CONTINUE;
            });
        } else {
            // Daemon is active
            if (this._isConnected) {
                // Connected: clicking main toggle disconnects device
                this._extension.callDaemonMethod('DisconnectDevice');
            } else {
                // Disconnected: clicking main toggle triggers reconnect burst and opens window
                this.subtitle = 'Buscando celular...';
                this._extension.callDaemonMethod('ReconnectDevice');
            }
        }
    }

    updateStatus(status) {
        if (!status) return;

        const daemonRunning = status.daemon_running !== undefined ? status.daemon_running : this._extension.isDaemonRunning();
        const isConnected = daemonRunning && (status.connected || status.state === 'CONNECTED');
        const devName = status.device_name || 'Celular';
        const battery = status.battery_level !== undefined ? status.battery_level : 0;
        const isCharging = status.is_charging || false;

        this._isConnected = isConnected;
        this.checked = isConnected;

        if (daemonRunning) {
            this._daemonToggleItem.label.text = 'Encerrar Serviço em 2º Plano';
            this._daemonToggleItem.setIcon('process-stop-symbolic');

            if (isConnected && status.device_name && status.device_name !== 'Nenhum dispositivo') {
                this.title = devName;
                this.subtitle = isCharging ? `⚡ ${battery}%` : `${battery}%`;
                this.iconName = 'phone-symbolic';

                this.menu.setHeader('phone-symbolic', devName, 'Conectado via Wi-Fi');
                this._deviceInfoItem.label.text = `${devName} (${status.device_model || 'Android'})`;
                
                let batteryIcon = 'battery-level-100-symbolic';
                if (isCharging) {
                    batteryIcon = 'battery-level-charging-symbolic';
                } else if (battery <= 20) {
                    batteryIcon = 'battery-level-20-symbolic';
                } else if (battery <= 60) {
                    batteryIcon = 'battery-level-60-symbolic';
                } else if (battery <= 80) {
                    batteryIcon = 'battery-level-80-symbolic';
                }
                this._batteryItem.setIcon(batteryIcon);
                this._batteryItem.label.text = `Bateria: ${battery}% ${isCharging ? '(Carregando)' : ''}`;
                this._mirrorItem.setSensitive(true);
            } else {
                this.title = 'ConnectToPhone';
                this.subtitle = 'Aguardando celular...';
                this.iconName = 'phone-symbolic';

                this.menu.setHeader('phone-symbolic', 'ConnectToPhone', 'Serviço ativo, aguardando conexão...');
                this._deviceInfoItem.label.text = 'Aguardando celular na rede local...';
                this._batteryItem.label.text = 'Bateria: --%';
                this._mirrorItem.setSensitive(false);
            }
        } else {
            this.title = 'Celular';
            this.subtitle = 'Desativado';
            this.iconName = 'phone-symbolic';

            this.menu.setHeader('phone-symbolic', 'ConnectToPhone', 'Serviço desativado');
            this._deviceInfoItem.label.text = 'Clique para ativar em segundo plano';
            this._batteryItem.label.text = 'Bateria: --%';
            this._mirrorItem.setSensitive(false);
            this._daemonToggleItem.label.text = 'Iniciar Serviço em 2º Plano';
            this._daemonToggleItem.setIcon('media-playback-start-symbolic');
        }

        if (status.sync_clipboard !== undefined) {
            this._clipSwitchItem.setToggleState(status.sync_clipboard);
        }
    }
});

const ConnectToPhoneIndicator = GObject.registerClass(
class ConnectToPhoneIndicator extends QuickSettings.SystemIndicator {
    _init(extension) {
        super._init();
        this._extension = extension;

        // Top bar indicator icon
        this._indicator = this._addIndicator();
        this._indicator.icon_name = 'phone-symbolic';
        this._indicator.visible = false;

        // Quick Settings Toggle Button
        this.quickSettingsToggle = new ConnectToPhoneToggle(extension);
        this.quickSettingsItems.push(this.quickSettingsToggle);

        this.connect('destroy', () => {
            this.quickSettingsToggle.destroy();
        });
    }

    updateStatus(status) {
        if (!status) return;
        const daemonRunning = status.daemon_running !== undefined ? status.daemon_running : this._extension.isDaemonRunning();
        const isConnected = daemonRunning && (status.connected || status.state === 'CONNECTED');
        this._indicator.visible = isConnected;
        this.quickSettingsToggle.updateStatus(status);
    }
});

export default class ConnectToPhoneExtension extends Extension {
    enable() {
        this._indicator = new ConnectToPhoneIndicator(this);
        Main.panel.statusArea.quickSettings.addExternalIndicator(this._indicator);

        this._dbusProxy = null;
        this._signalId = 0;
        this._ownerSignalId = 0;
        this._selectionId = 0;
        this._pollTimerId = 0;

        this._initDBus();
        this._setupClipboardWatcher();

        // 3-second heartbeat to ensure status and battery are always synced live
        this._pollTimerId = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 3, () => {
            this.fetchStatus();
            return GLib.SOURCE_CONTINUE;
        });
    }

    disable() {
        if (this._pollTimerId) {
            GLib.source_remove(this._pollTimerId);
            this._pollTimerId = 0;
        }

        if (this._selectionId) {
            try {
                const display = global.get_display();
                const selection = display.get_selection();
                selection.disconnect(this._selectionId);
            } catch (e) {
                // Ignore cleanup error
            }
            this._selectionId = 0;
        }

        if (this._signalId && this._dbusProxy) {
            this._dbusProxy.disconnect(this._signalId);
            this._signalId = 0;
        }
        if (this._ownerSignalId && this._dbusProxy) {
            this._dbusProxy.disconnect(this._ownerSignalId);
            this._ownerSignalId = 0;
        }
        this._dbusProxy = null;

        if (this._indicator) {
            this._indicator.destroy();
            this._indicator = null;
        }
    }

    isDaemonRunning() {
        return !!(this._dbusProxy && this._dbusProxy.g_name_owner);
    }

    _setupClipboardWatcher() {
        try {
            const display = global.get_display();
            if (display) {
                const selection = display.get_selection();
                if (selection) {
                    this._selectionId = selection.connect('owner-changed', (sel, selType, source) => {
                        if (selType === Meta.SelectionType.SELECTION_CLIPBOARD) {
                            St.Clipboard.get_default().get_text(St.ClipboardType.CLIPBOARD, (cb, text) => {
                                if (text && text.length > 0) {
                                    this.callDaemonMethod('ReportClipboardText', new GLib.Variant('(s)', [text]));
                                }
                            });
                        }
                    });
                }
            }
        } catch (e) {
            console.log(`[ConnectToPhone] Selection watcher error: ${e}`);
        }
    }

    _initDBus() {
        try {
            Gio.DBusProxy.new_for_bus(
                Gio.BusType.SESSION,
                Gio.DBusProxyFlags.NONE,
                null,
                DBUS_NAME,
                DBUS_PATH,
                DBUS_INTERFACE,
                null,
                (initable, result) => {
                    try {
                        this._dbusProxy = Gio.DBusProxy.new_for_bus_finish(result);
                        
                        // Listen for status changes from daemon
                        this._signalId = this._dbusProxy.connect('g-signal', (proxy, senderName, signalName, parameters) => {
                            if (signalName === 'StatusChanged') {
                                try {
                                    const unpacked = parameters.recursiveUnpack ? parameters.recursiveUnpack() : parameters.deep_unpack();
                                    const statusJson = Array.isArray(unpacked) ? unpacked[0] : parameters.get_child_value(0).get_string()[0];
                                    const status = JSON.parse(statusJson);
                                    status.daemon_running = true;
                                    if (this._indicator) {
                                        this._indicator.updateStatus(status);
                                    }
                                } catch (e) {
                                    console.error(`[ConnectToPhone] Status parse error: ${e}`);
                                }
                            }
                        });

                        // Listen for daemon connect / disconnect on bus
                        this._ownerSignalId = this._dbusProxy.connect('notify::g-name-owner', () => {
                            if (this._dbusProxy.g_name_owner) {
                                this.fetchStatus();
                            } else if (this._indicator) {
                                this._indicator.updateStatus({ connected: false, daemon_running: false });
                            }
                        });

                        if (this._dbusProxy.g_name_owner) {
                            this.fetchStatus();
                        } else {
                            if (this._indicator) {
                                this._indicator.updateStatus({ connected: false, daemon_running: false });
                            }
                        }
                    } catch (e) {
                        console.log(`[ConnectToPhone] DBus init error: ${e}`);
                    }
                }
            );
        } catch (e) {
            console.log(`[ConnectToPhone] Error setting up DBusProxy: ${e}`);
        }
    }

    fetchStatus() {
        if (!this._dbusProxy || !this._dbusProxy.g_name_owner) {
            if (this._indicator) {
                this._indicator.updateStatus({ connected: false, daemon_running: false });
            }
            return;
        }

        this._dbusProxy.call(
            'GetStatus',
            new GLib.Variant('()', []),
            Gio.DBusCallFlags.NONE,
            -1,
            null,
            (proxy, res) => {
                try {
                    const result = proxy.call_finish(res);
                    const unpacked = result.recursiveUnpack ? result.recursiveUnpack() : result.deep_unpack();
                    const statusJson = Array.isArray(unpacked) ? unpacked[0] : result.get_child_value(0).get_string()[0];
                    const status = JSON.parse(statusJson);
                    status.daemon_running = true;
                    if (this._indicator) {
                        this._indicator.updateStatus(status);
                    }
                } catch (e) {
                    console.log(`[ConnectToPhone] Error in GetStatus: ${e}`);
                }
            }
        );
    }

    callDaemonMethod(methodName, parameters = null) {
        const variantParams = parameters || new GLib.Variant('()', []);
        
        if (this._dbusProxy && this._dbusProxy.g_name_owner) {
            this._dbusProxy.call(
                methodName,
                variantParams,
                Gio.DBusCallFlags.NONE,
                -1,
                null,
                (proxy, res) => {
                    try {
                        proxy.call_finish(res);
                    } catch (e) {
                        console.log(`[ConnectToPhone] Error calling ${methodName}: ${e}`);
                        if (methodName !== 'ReportClipboardText' && methodName !== 'ReportClipboardImage') {
                            this._launchAppProcess(methodName);
                        }
                    }
                }
            );
        } else if (methodName !== 'ReportClipboardText' && methodName !== 'ReportClipboardImage') {
            this._launchAppProcess(methodName);
        }
    }

    startDaemon() {
        this._launchAppProcess('Daemon');
    }

    stopDaemon() {
        this.callDaemonMethod('Quit');
    }

    _launchAppProcess(methodName = 'OpenWindow') {
        try {
            let flag = '';
            if (methodName === 'OpenMirror') {
                flag = '--mirror';
            } else if (methodName === 'OpenPairDialog') {
                flag = '--pair';
            } else if (methodName === 'Daemon') {
                flag = '--daemon';
            }
            const cmd = `python3 /home/erich/Documentos/GitHub/ConnectToPhone/desktop/main.py ${flag}`.trim();
            const app = Gio.AppInfo.create_from_commandline(
                cmd,
                'ConnectToPhone',
                Gio.AppInfoCreateFlags.NONE
            );
            if (app) {
                app.launch([], null);
            }
        } catch (e) {
            console.error(`[ConnectToPhone] Error launching app: ${e}`);
        }
    }
}

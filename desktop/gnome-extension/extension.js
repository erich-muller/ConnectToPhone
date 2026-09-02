import GObject from 'gi://GObject';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import St from 'gi://St';
import Clutter from 'gi://Clutter';
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
            subtitle: 'Desconectado',
            iconName: 'phone-symbolic',
            toggleMode: false,
        });

        this._extension = extension;
        this.menu.setHeader('phone-symbolic', 'ConnectToPhone', 'Aguardando celular...');

        this._buildMenu();
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
    }

    updateStatus(status) {
        if (!status) return;

        const isConnected = status.connected || (status.state === 'CONNECTED');
        const devName = status.device_name || 'Celular';
        const battery = status.battery_level || 0;
        const isCharging = status.is_charging || false;

        this.checked = isConnected;

        if (isConnected) {
            this.title = devName;
            this.subtitle = isCharging ? `⚡ ${battery}% (Carregando)` : `${battery}%`;
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
            this.title = 'Celular';
            this.subtitle = 'Desconectado';
            this.iconName = 'phone-symbolic';

            this.menu.setHeader('phone-symbolic', 'ConnectToPhone', 'Aguardando celular na rede local...');
            this._deviceInfoItem.label.text = 'Nenhum aparelho conectado';
            this._batteryItem.label.text = 'Bateria: --%';
            this._mirrorItem.setSensitive(false);
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
        const isConnected = status.connected || (status.state === 'CONNECTED');
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
        this._initDBus();
    }

    disable() {
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
                                const [statusJson] = parameters.unpack();
                                try {
                                    const status = JSON.parse(statusJson);
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
                                this._fetchInitialStatus();
                            } else if (this._indicator) {
                                this._indicator.updateStatus({ connected: false, state: 'DISCONNECTED' });
                            }
                        });

                        if (this._dbusProxy.g_name_owner) {
                            this._fetchInitialStatus();
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

    _fetchInitialStatus() {
        if (!this._dbusProxy) return;
        this._dbusProxy.call(
            'GetStatus',
            new GLib.Variant('()', []),
            Gio.DBusCallFlags.NONE,
            -1,
            null,
            (proxy, res) => {
                try {
                    const result = proxy.call_finish(res);
                    const [statusJson] = result.unpack();
                    const status = JSON.parse(statusJson);
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
                        this._launchAppProcess(methodName);
                    }
                }
            );
        } else {
            console.log(`[ConnectToPhone] Daemon not running on bus, launching app for ${methodName}`);
            this._launchAppProcess(methodName);
        }
    }

    _launchAppProcess(methodName = 'OpenWindow') {
        try {
            let flag = '';
            if (methodName === 'OpenMirror') {
                flag = '--mirror';
            } else if (methodName === 'OpenPairDialog') {
                flag = '--pair';
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

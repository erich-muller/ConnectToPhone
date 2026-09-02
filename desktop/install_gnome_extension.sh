#!/usr/bin/env bash
# ConnectToPhone - Install and Enable GNOME Shell Extension, Desktop Launcher & Autostart
set -e

EXT_UUID="connect-to-phone@erich.github.com"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXT_SRC_DIR="${SCRIPT_DIR}/gnome-extension"
EXT_DEST_DIR="${HOME}/.local/share/gnome-shell/extensions/${EXT_UUID}"
APPS_DIR="${HOME}/.local/share/applications"
AUTOSTART_DIR="${HOME}/.config/autostart"

echo "📦 Instalando Extensão GNOME Shell do ConnectToPhone..."

# 1. Direct copy to extensions directory
mkdir -p "${EXT_DEST_DIR}"
cp -rf "${EXT_SRC_DIR}/"* "${EXT_DEST_DIR}/"
echo "✅ Arquivos copiados para: ${EXT_DEST_DIR}"

# 2. Package and install via gnome-extensions CLI
if command -v gnome-extensions >/dev/null 2>&1; then
    TMP_ZIP="/tmp/${EXT_UUID}.shell-extension.zip"
    gnome-extensions pack "${EXT_SRC_DIR}" --force --out-dir=/tmp/ >/dev/null 2>&1 || true
    if [ -f "${TMP_ZIP}" ]; then
        gnome-extensions install --force "${TMP_ZIP}" >/dev/null 2>&1 || true
        rm -f "${TMP_ZIP}"
    fi
fi

# 3. Create desktop entry in ~/.local/share/applications
mkdir -p "${APPS_DIR}"
cat <<EOF > "${APPS_DIR}/org.connecttophone.Desktop.desktop"
[Desktop Entry]
Name=ConnectToPhone
Comment=Vincular e sincronizar celular Android no Linux GNOME
Exec=python3 ${SCRIPT_DIR}/main.py
Icon=${SCRIPT_DIR}/assets/phone.svg
Terminal=false
Type=Application
Categories=Utility;Network;GNOME;GTK;
StartupNotify=true
StartupWMClass=org.connecttophone.Desktop
EOF
chmod +x "${APPS_DIR}/org.connecttophone.Desktop.desktop"
echo "✅ Desktop Entry criado em: ${APPS_DIR}/org.connecttophone.Desktop.desktop"

# 4. Create Autostart Entry in ~/.config/autostart (runs in background on user login)
mkdir -p "${AUTOSTART_DIR}"
cat <<EOF > "${AUTOSTART_DIR}/org.connecttophone.Desktop.desktop"
[Desktop Entry]
Name=ConnectToPhone Daemon
Comment=Serviço em segundo plano do ConnectToPhone
Exec=python3 ${SCRIPT_DIR}/main.py --daemon
Icon=${SCRIPT_DIR}/assets/phone.svg
Terminal=false
Type=Application
Categories=Utility;Network;
X-GNOME-Autostart-enabled=true
EOF
echo "✅ Inicialização automática em segundo plano configurada em: ${AUTOSTART_DIR}/org.connecttophone.Desktop.desktop"

# 5. Enable extension in GSettings
if command -v gsettings >/dev/null 2>&1; then
    python3 -c "
import subprocess, ast
try:
    res = subprocess.run(['gsettings', 'get', 'org.gnome.shell', 'enabled-extensions'], capture_output=True, text=True, check=True)
    exts = ast.literal_eval(res.stdout.strip())
    if '${EXT_UUID}' not in exts:
        exts.append('${EXT_UUID}')
        subprocess.run(['gsettings', 'set', 'org.gnome.shell', 'enabled-extensions', str(exts)], check=True)
except Exception:
    pass
" || true
fi

# 6. Try enabling via gnome-extensions command
if command -v gnome-extensions >/dev/null 2>&1; then
    gnome-extensions enable "${EXT_UUID}" 2>/dev/null || true
fi

echo "🎉 Instalação e configuração de segundo plano concluídas com sucesso!"

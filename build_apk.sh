#!/usr/bin/env bash
# ==============================================================================
# Script para compilar o APK do ConnectToPhone no Linux sem o Android Studio
# ==============================================================================
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

# Definir JDK completo se disponível no sistema
if [ -d "$HOME/.jdks/jbr-21.0.11" ]; then
    export JAVA_HOME="$HOME/.jdks/jbr-21.0.11"
    export PATH="$JAVA_HOME/bin:$PATH"
fi

export ANDROID_HOME="$HOME/Android/Sdk"
export ANDROID_SDK_ROOT="$HOME/Android/Sdk"

cd "$DIR/android"

# Garantir permissão de execução no gradlew
chmod +x ./gradlew

echo "📦 Compilando APK do ConnectToPhone..."
./gradlew assembleDebug

APK_PATH="$DIR/android/app/build/outputs/apk/debug/app-debug.apk"

if [ -f "$APK_PATH" ]; then
    echo ""
    echo "======================================================================"
    echo "✅ APK GERADO COM SUCESSO!"
    echo "📁 Localização: $APK_PATH"
    echo "======================================================================"
    echo ""
    echo "📱 Como instalar no seu Android:"
    echo "1. Via USB com ADB (se a Depuração USB estiver ativa):"
    echo "   adb install -r $APK_PATH"
    echo ""
    echo "2. Diretamente no aparelho:"
    echo "   Transfira o arquivo 'app-debug.apk' para o celular (via cabo USB,"
    echo "   email ou armazenamento compartilhado) e toque nele para instalar."
else
    echo "❌ Erro ao localizar o arquivo APK após a compilação."
    exit 1
fi

# ConnectToPhone 📱 ⇄ 💻

Aplicativo de integração contínua entre **Linux** e aparelhos **Android** operando exclusivamente via **Rede Local (Wi-Fi / LAN)** sem depender de conexão com a internet. Inspirado no "Vincular ao Celular" (*Phone Link*) do Windows.

---

## ✨ Funcionalidades

1. **🖥️ Espelhamento de Tela em Tempo Real**:
   - Janela dedicada no Linux com baixa latência e **adaptação dinâmica automática de orientação** (Retrato ⇄ Paisagem sem distorções).
   - Suporte completo a interação pelo PC: **cliques (toques), arrastes (swipes), rolagem pelo scroll do mouse e digitação de teclado**.
   - Design limpo e minimalista com indicador de FPS/Resolução e modo Tela Cheia.

2. **📋 Sincronização Bidirecional da Área de Transferência**:
   - **Texto e Imagens**: Sincronização em tempo real entre Linux e Android sem necessidade de intervenção manual.
   - Histórico visual no dashboard com botões azuis sólidos de cópia rápida.

3. **⚡ Operação Contínua em Segundo Plano**:
   - **No Linux**: Fechar a janela principal oculta o aplicativo para a **bandeja do sistema (*System Tray*)**, mantendo as sincronizações e conexões ativas continuamente.
   - **No Android**: *Foreground Service* persistente com auto-reconexão no Wi-Fi e inicialização automática no boot.

4. **🎨 Ícones e Aparência Personalizáveis**:
   - Paleta moderna em tons de cinza fosco (`#18181B`) com detalhes sólidos em azul e verde.
   - Suporte a imagens personalizadas para ícones em `desktop/assets/` (`app_icon.png`, `tray_connected.png`, etc.).

---

## 🚀 Como Executar no Linux

```bash
# Instalar dependências
pip install -r requirements.txt

# Executar aplicação
python3 desktop/main.py
```
*(Para fechar completamente a aplicação, clique com o botão direito no ícone da bandeja do sistema e selecione "Sair")*

---

## 📱 Como Compilar e Instalar no Android (Sem Android Studio)

Criamos um script automático para gerar o arquivo `.apk` diretamente pelo terminal:

### 1. Compilar o APK:
Na raiz do projeto, execute:
```bash
./build_apk.sh
```
O arquivo será gerado em:
`android/app/build/outputs/apk/debug/app-debug.apk`

### 2. Instalar no Aparelho:

**Opção A — Via USB com ADB (Mais rápido se a Depuração USB estiver ativa):**
```bash
adb install -r android/app/build/outputs/apk/debug/app-debug.apk
```

**Opção B — Transferência Direta do Arquivo:**
1. Conecte o celular via cabo USB ao computador (ou envie o arquivo `app-debug.apk` para o seu aparelho via email, nuvem local ou Bluetooth).
2. No celular, abra o gerenciador de arquivos (*Meus Arquivos / Files*), localize o `app-debug.apk` e toque nele.
3. Se o Android solicitar permissão, ative **"Permitir desta fonte"** (Instalar apps desconhecidos) e confirme a instalação.
4. Abra o **ConnectToPhone**, escaneie o QR Code na tela do seu Linux e ative o serviço de acessibilidade/gestos para ter controle total do mouse/teclado!

---

## 🎨 Personalização de Ícones

Basta colocar suas próprias imagens PNG na pasta [`desktop/assets/`](file:///home/erich/Documentos/ConnectToPhone/desktop/assets/):

| Arquivo | Descrição | Tamanho Recomendado |
| :--- | :--- | :--- |
| **`app_icon.png`** | Ícone principal das janelas e do aplicativo | **512x512** ou **256x256 px** |
| **`tray_connected.png`** | Ícone do tray quando o celular está conectado | **64x64** ou **32x32 px** |
| **`tray_disconnected.png`** | Ícone do tray quando desconectado/aguardando | **64x64** ou **32x32 px** |
| **`tray_icon.png`** | Ícone genérico de fallback | **64x64 px** |

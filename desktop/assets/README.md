# Ícones Personalizados do ConnectToPhone

Você pode personalizar todos os ícones da aplicação substituindo os arquivos de imagem nesta pasta (`desktop/assets/`):

---

## 📁 Arquivos Suportados e Tamanhos Recomendados

| Arquivo | Descrição | Formato | Dimensões Recomendadas |
| :--- | :--- | :--- | :--- |
| **`app_icon.png`** | Ícone principal do aplicativo e das janelas (Desktop / Barra de tarefas / Janelas) | PNG (transparente) | **512x512** ou **256x256 px** |
| **`tray_connected.png`** | Ícone exibido na bandeja do sistema (*System Tray*) quando o celular está **conectado** | PNG (transparente) | **64x64** ou **32x32 px** |
| **`tray_disconnected.png`** | Ícone exibido na bandeja do sistema quando está **aguardando conexão ou desconectado** | PNG (transparente) | **64x64** ou **32x32 px** |
| **`tray_icon.png`** | Ícone genérico de fallback para a bandeja do sistema | PNG (transparente) | **64x64** ou **32x32 px** |

---

## 💡 Dicas de Customização:
1. **Fundo Transparente**: Use arquivos `.png` com canal alfa (fundo transparente) para que se integrem perfeitamente ao tema do seu painel do Linux (GNOME, KDE Plasma, XFCE, etc.).
2. **Atualização Imediata**: Basta colar a imagem com o nome correspondente nesta pasta e reiniciar o aplicativo (`python3 desktop/main.py`).
3. **Fallback Automático**: Se você remover ou renomear algum arquivo, o sistema volta a desenhar automaticamente o ícone vetorial padrão.

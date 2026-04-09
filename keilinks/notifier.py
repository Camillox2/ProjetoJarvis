"""
Notificações nativas do Windows (toast) + som de alerta.
A Keilinks pode te avisar mesmo quando a janela tá minimizada.
"""

import threading
from pathlib import Path
from keilinks.log import get_logger

log = get_logger("notifier")


def notify(title: str, message: str, duration: int = 5):
    """Envia uma notificação toast do Windows em background."""
    threading.Thread(
        target=_send_toast, args=(title, message, duration), daemon=True
    ).start()


def _send_toast(title: str, message: str, duration: int):
    try:
        from winotify import Notification, audio
        toast = Notification(
            app_id="Keilinks",
            title=title,
            msg=message,
            duration="short" if duration <= 5 else "long",
        )
        toast.set_audio(audio.Default, loop=False)
        toast.show()
    except ImportError:
        # Fallback: notificação via PowerShell (sem dependência extra)
        _powershell_toast(title, message)
    except Exception as e:
        log.error("%s: %s (erro: %s)", title, message, e)


def _powershell_toast(title: str, message: str):
    import subprocess
    # Sanitiza aspas simples para prevenir injeção de comando PowerShell
    safe_title   = title.replace("'", "''")
    safe_message = message.replace("'", "''")
    script = f"""
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent(
        [Windows.UI.Notifications.ToastTemplateType]::ToastText02)
    $template.SelectSingleNode('//text[@id="1"]').InnerText = '{safe_title}'
    $template.SelectSingleNode('//text[@id="2"]').InnerText = '{safe_message}'
    $toast = [Windows.UI.Notifications.ToastNotification]::new($template)
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Keilinks').Show($toast)
    """
    try:
        subprocess.run(["powershell", "-Command", script], capture_output=True, timeout=5)
    except Exception:
        pass

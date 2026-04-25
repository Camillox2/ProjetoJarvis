"""
Visão da Keilinks: câmera física + captura de tela.
Ambas retornam base64 JPEG para o qwen3-vl:8b analisar.
"""

import base64
import os
import cv2
import numpy as np
from datetime import datetime
from pathlib import Path
from config import CAMERA_INDEX, CAMERA_ENABLED
from keilinks.log import get_logger

log = get_logger("eyes")


class Eyes:
    def __init__(self):
        self.cap = None
        if CAMERA_ENABLED:
            self._init_camera()

    def _init_camera(self):
        import platform
        # No Windows, CAP_DSHOW garante que o LED da câmera acende e evita falha silenciosa
        backend = cv2.CAP_DSHOW if platform.system() == "Windows" else cv2.CAP_ANY
        self.cap = cv2.VideoCapture(CAMERA_INDEX, backend)
        if not self.cap.isOpened():
            # Tenta sem backend específico como fallback
            self.cap = cv2.VideoCapture(CAMERA_INDEX)
        if not self.cap.isOpened():
            log.warning("Câmera não encontrada (índice=%d). Continuando sem visão ao vivo.", CAMERA_INDEX)
            self.cap = None
        else:
            # 640x480 é suficiente para análise VLM — menos VRAM e mais rápido
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            log.info("Câmera iniciada (índice=%d, %dx%d).", CAMERA_INDEX, 640, 480)

    # ─── Câmera física ────────────────────────────────────────────────────────
    def capture_frame(self) -> np.ndarray | None:
        """Retorna o frame atual como array BGR. Mais eficiente para processamento local (sem codificação)."""
        if self.cap is None or not self.cap.isOpened():
            return None
        ret, frame = self.cap.read()
        return frame if ret else None

    def capture_frame_b64(self) -> str | None:
        if self.cap is None or not self.cap.isOpened():
            log.warning("[VISION] capture_frame_b64: câmera None ou fechada.")
            return None
        ret, frame = self.cap.read()
        if not ret or frame is None:
            log.warning("[VISION] capture_frame_b64: cap.read() falhou (ret=%s).", ret)
            return None
        h, w = frame.shape[:2]
        log.debug("[VISION] Frame capturado: %dx%d px", w, h)
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not ok:
            log.error("[VISION] cv2.imencode falhou para o frame.")
            return None
        return base64.b64encode(buf).decode("utf-8")

    # ─── Captura de tela ──────────────────────────────────────────────────────
    def capture_screen_b64(self, monitor: int = 1) -> str | None:
        """
        Captura a tela inteira (ou um monitor específico) e retorna base64.
        monitor=1 = monitor principal.
        """
        try:
            import mss
            with mss.mss() as sct:
                mon = sct.monitors[monitor]
                img = sct.grab(mon)
                # mss retorna BGRA, converte pra BGR
                frame = np.array(img)[:, :, :3]
                # Reduz resolução pela metade (economiza tokens do LLM)
                h, w = frame.shape[:2]
                frame = cv2.resize(frame, (w // 2, h // 2))
                _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
                return base64.b64encode(buf).decode("utf-8")
        except ImportError:
            log.warning("Instale 'mss' para captura de tela: pip install mss")
            return None
        except Exception as e:
            log.error("Erro ao capturar tela: %s", e)
            return None

    def save_screenshot(self) -> str | None:
        """Salva screenshot em disco e retorna o caminho."""
        try:
            import mss
            path = Path("prints")
            path.mkdir(exist_ok=True)
            filename = path / f"print_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            with mss.mss() as sct:
                sct.shot(output=str(filename))
            return str(filename)
        except Exception as e:
            log.error("Erro ao salvar print: %s", e)
            return None

    # ─── OCR — lê texto da tela ───────────────────────────────────────────────
    def read_screen_text(self, lang: str = "por+eng") -> str | None:
        """
        Captura a tela e extrai o texto visível via OCR (pytesseract).
        Retorna o texto limpo, ou None se pytesseract não estiver instalado.
        """
        try:
            import pytesseract
        except ImportError:
            log.warning("Instale pytesseract + Tesseract OCR para usar OCR.")
            return None

        frame = self._capture_raw()
        if frame is None:
            return None

        # Pré-processamento: escala de cinza + nitidez → melhora OCR
        gray    = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        sharp   = cv2.filter2D(gray, -1, np.array([[-1,-1,-1],[-1,9,-1],[-1,-1,-1]]))

        try:
            text = pytesseract.image_to_string(sharp, lang=lang, config="--psm 6")
        except Exception:
            # Se não tiver o pacote de idioma pt, usa só inglês
            text = pytesseract.image_to_string(sharp, config="--psm 6")

        # Limpa: remove linhas em branco e lixo de OCR
        lines = [l.strip() for l in text.splitlines() if len(l.strip()) > 2]
        return "\n".join(lines) if lines else ""

    def _capture_raw(self) -> np.ndarray | None:
        """Captura tela em tamanho original (sem redução) para OCR preciso."""
        try:
            import mss
            with mss.mss() as sct:
                mon = sct.monitors[1]
                img = sct.grab(mon)
                return np.array(img)[:, :, :3]
        except Exception as e:
            log.error("Erro ao capturar tela para OCR: %s", e)
            return None

    def is_available(self) -> bool:
        return self.cap is not None and self.cap.isOpened()

    def release(self):
        if self.cap:
            self.cap.release()
        cv2.destroyAllWindows()

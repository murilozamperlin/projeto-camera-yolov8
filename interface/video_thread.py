import threading
import time

import cv2
import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtGui import QImage
from ultralytics import YOLO


def hex_para_bgr(cor_hex):
    """Converte #RRGGBB para BGR; usa vermelho se o valor for inválido."""
    try:
        cor_hex = str(cor_hex).lstrip("#")
        if len(cor_hex) != 6:
            raise ValueError("cor inválida")
        r, g, b = (int(cor_hex[i:i + 2], 16) for i in (0, 2, 4))
        return (b, g, r)
    except (TypeError, ValueError):
        return (0, 0, 255)


class VideoThread(QThread):
    frame_signal = pyqtSignal(QImage)
    status_signal = pyqtSignal(str)
    alert_signal = pyqtSignal(bool)
    metrics_signal = pyqtSignal(float, int, float)  # FPS, pessoas, inferência (ms)
    pessoas_zona_signal = pyqtSignal(int)            # pessoas em pelo menos uma zona

    def __init__(self, camera_source=0, model_path="yolo26n.pt", zona=None,
                 zonas=None, confianca=0.50):
        super().__init__()
        self.camera_source = camera_source
        self.model_path = model_path
        self._running = True
        self._paused = False
        self._zone_lock = threading.Lock()
        if zonas is None:
            zonas = [zona] if zona is not None else []
        self._zonas = self._normalizar_zonas(zonas)
        self._conf = float(confianca)

    @staticmethod
    def _normalizar_zona(zona):
        try:
            if isinstance(zona, dict):
                vertices = zona.get("vertices", [])
                cor = zona.get("cor", zona.get("color", "#dc2626"))
            else:
                vertices, cor = zona
            pontos = [(float(p[0]), float(p[1])) for p in vertices]
            if len(pontos) < 3 or any(
                not (np.isfinite(x) and np.isfinite(y) and 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0)
                for x, y in pontos
            ):
                return None
            if len(str(cor).lstrip("#")) != 6:
                cor = "#dc2626"
            hex_para_bgr(cor)
            return (pontos, str(cor))
        except (TypeError, ValueError, IndexError):
            return None

    @classmethod
    def _normalizar_zonas(cls, zonas):
        resultado = []
        for zona in zonas or []:
            item = cls._normalizar_zona(zona)
            if item is not None:
                resultado.append(item)
        return resultado

    def definir_zonas(self, zonas):
        """Substitui a lista de polígonos sem bloquear a thread de vídeo."""
        normalizadas = self._normalizar_zonas(zonas)
        with self._zone_lock:
            self._zonas = normalizadas

    def definir_zona(self, pontos_norm, cor):
        """Compatibilidade com chamadas antigas de zona única."""
        self.definir_zonas([(pontos_norm, cor)])

    def limpar_zona(self):
        self.definir_zonas([])

    def definir_confianca(self, valor):
        self._conf = float(valor)

    @staticmethod
    def _montar_poligono(zona, largura, altura):
        pontos_norm, cor = zona
        pts = [
            (round(x * max(0, largura - 1)), round(y * max(0, altura - 1)))
            for x, y in pontos_norm
        ]
        return np.asarray(pts, dtype=np.int32).reshape((-1, 1, 2))

    def run(self):
        self.status_signal.emit("Carregando modelo YOLO26n...")
        try:
            model = YOLO(self.model_path)
        except Exception as e:
            self.status_signal.emit(f"Erro ao carregar modelo: {e}")
            return

        self.status_signal.emit("Conectando à webcam...")
        cap = cv2.VideoCapture(self.camera_source, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap.release()
            cap = cv2.VideoCapture(self.camera_source)
        if not cap.isOpened():
            cap.release()
            self.status_signal.emit("Erro: Webcam não encontrada.")
            return

        self.status_signal.emit("Câmera conectada")
        ultimo_alerta = None
        ultimo_dentro = None
        ultimo_tempo_fps = time.perf_counter()
        quadros_no_intervalo = 0
        fps_atual = 0.0

        while self._running:
            if self._paused:
                self.msleep(100)
                continue

            ret, frame = cap.read()
            if not ret:
                self.status_signal.emit("Falha na leitura da webcam.")
                self.msleep(200)
                continue

            inicio_inferencia = time.perf_counter()
            result = model(frame, conf=self._conf, classes=[0], verbose=False)[0]
            inferencia_ms = (time.perf_counter() - inicio_inferencia) * 1000
            annotated_frame = result.plot()
            altura, largura = frame.shape[:2]

            with self._zone_lock:
                zonas = list(self._zonas)
            poligonos = [
                (self._montar_poligono(zona, largura, altura), zona[1])
                for zona in zonas
            ]

            caixas = result.boxes.xyxy.cpu().numpy() if result.boxes is not None else []
            quantidade_pessoas = len(caixas)
            dentro = 0
            for caixa in caixas:
                x1, y1, x2, y2 = caixa[:4]
                ponto_pe = (int((x1 + x2) / 2), int(y2))
                cor_ponto = None
                for poligono, cor in poligonos:
                    if cv2.pointPolygonTest(poligono, ponto_pe, False) >= 0:
                        cor_ponto = cor
                        break
                if cor_ponto is not None:
                    dentro += 1
                    cv2.circle(annotated_frame, ponto_pe, 7, hex_para_bgr(cor_ponto), -1)

            alerta = dentro > 0
            if dentro != ultimo_dentro:
                self.pessoas_zona_signal.emit(dentro)
                ultimo_dentro = dentro
            if alerta != ultimo_alerta:
                self.alert_signal.emit(alerta)
                ultimo_alerta = alerta

            quadros_no_intervalo += 1
            agora = time.perf_counter()
            duracao = agora - ultimo_tempo_fps
            if duracao >= 1.0:
                fps_atual = quadros_no_intervalo / duracao
                quadros_no_intervalo = 0
                ultimo_tempo_fps = agora

            self.metrics_signal.emit(fps_atual, quantidade_pessoas, inferencia_ms)
            rgb_image = cv2.cvtColor(annotated_frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb_image.shape
            qt_image = QImage(rgb_image.data, w, h, ch * w, QImage.Format_RGB888).copy()
            self.frame_signal.emit(qt_image)

        cap.release()
        self.status_signal.emit("Transmissão encerrada")

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    def stop(self):
        self._running = False
        self.wait()

import math
import os
import time

os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")

import cv2
import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtGui import QImage
from ultralytics import YOLO


class VideoThread(QThread):
    frame_signal = pyqtSignal(QImage)
    status_signal = pyqtSignal(str)
    alert_signal = pyqtSignal(bool)
    metrics_signal = pyqtSignal(float, int, float)

    def __init__(self, camera_source=0, model_path="yolo26n.pt", zona=None):
        super().__init__()
        self.camera_source = camera_source
        self.model_path = model_path
        self._running = True
        self._paused = False
        self._zona = self._normalizar_zona(zona)

    @staticmethod
    def _retangulo_em_vertices(zona):
        cx, cy, w, h, angulo = map(float, zona)
        a = math.radians(angulo)
        c, s = math.cos(a), math.sin(a)
        return [
            (cx + dx*c - dy*s, cy + dx*s + dy*c)
            for dx, dy in ((-w/2, -h/2), (w/2, -h/2),
                           (w/2, h/2), (-w/2, h/2))
        ]

    @classmethod
    def _normalizar_zona(cls, zona):
        if zona is None:
            return None
        if isinstance(zona, dict):
            if "vertices" in zona:
                zona = zona["vertices"]
            elif all(k in zona for k in ("centro_x", "centro_y", "largura", "altura")):
                zona = cls._retangulo_em_vertices((
                    zona["centro_x"], zona["centro_y"], zona["largura"],
                    zona["altura"], zona.get("angulo", 0.0)
                ))
        if isinstance(zona, (list, tuple)) and len(zona) == 5 and all(
            isinstance(v, (int, float)) for v in zona
        ):
            zona = cls._retangulo_em_vertices(zona)
        elif isinstance(zona, (list, tuple)) and len(zona) == 4 and all(
            isinstance(v, (int, float)) for v in zona
        ):
            x1, y1, x2, y2 = map(float, zona)
            zona = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
        try:
            vertices = [(float(p[0]), float(p[1])) for p in zona]
        except (TypeError, ValueError, IndexError):
            return None
        if len(vertices) < 3 or any(
            not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0) for x, y in vertices
        ):
            return None
        area2 = sum(
            x1*y2 - x2*y1
            for (x1, y1), (x2, y2) in zip(vertices, vertices[1:] + vertices[:1])
        )
        return vertices if abs(area2) >= 0.001 else None

    def definir_zona(self, vertices):
        """Define um polígono por vértices normalizados (x,y entre 0 e 1)."""
        self._zona = self._normalizar_zona(vertices)

    def limpar_zona(self):
        """Remove a zona de perigo (nenhum alerta será gerado)."""
        self._zona = None

    @staticmethod
    def _montar_poligono(zona, largura, altura):
        vertices = VideoThread._normalizar_zona(zona)
        if vertices is None:
            return None
        pts = [
            (round(x * max(0, largura - 1)), round(y * max(0, altura - 1)))
            for x, y in vertices
        ]
        return np.array(pts, dtype=np.int32).reshape((-1, 1, 2))

    def _abrir_captura(self):
        """Abre RTSP via FFmpeg/TCP com timeouts; webcam fica opcional."""
        fonte = self.camera_source
        rtsp = isinstance(fonte, str) and fonte.strip().lower().startswith(
            ("rtsp://", "rtsps://")
        )

        if rtsp:
            cap = cv2.VideoCapture()
            parametros = [
                cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000,
                cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000,
            ]
            try:
                # Não há fallback para uma abertura sem timeout: isso era o que
                # causava esperas adicionais de aproximadamente 30 segundos.
                cap.open(fonte, cv2.CAP_FFMPEG, parametros)
            except (AttributeError, TypeError, cv2.error):
                cap.release()
                return cv2.VideoCapture()

            if cap.isOpened():
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            return cap

        if isinstance(fonte, str) and fonte.strip().isdigit():
            fonte = int(fonte.strip())

        cap = cv2.VideoCapture(fonte, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap.release()
            cap = cv2.VideoCapture(fonte)
        return cap

    def run(self):
        self.status_signal.emit("Carregando modelo YOLO26n...")
        try:
            model = YOLO(self.model_path)
        except Exception as e:
            self.status_signal.emit(f"Erro ao carregar modelo: {e}")
            return

        self.status_signal.emit("Conectando à câmera configurada...")
        cap = self._abrir_captura()

        if not cap.isOpened():
            self.status_signal.emit(
                "Não foi possível abrir o RTSP em até 5 s. Verifique IP, rede, "
                "porta 554, credenciais e se o RTSP está habilitado."
            )
            cap.release()
            return

        self.status_signal.emit("Câmera conectada")
        ultimo_alerta = None
        ultimo_tempo_fps = time.perf_counter()
        quadros_no_intervalo = 0
        fps_atual = 0.0

        while self._running:
            if self._paused:
                self.msleep(100)
                continue

            ret, frame = cap.read()
            if not ret:
                self.status_signal.emit(
                    "Sinal de vídeo perdido; tentando reconectar..."
                )
                cap.release()
                reconectou = False

                # No máximo três tentativas, cada uma com timeout de abertura.
                for _ in range(3):
                    if not self._running:
                        break
                    self.msleep(800)
                    cap = self._abrir_captura()
                    if cap.isOpened():
                        reconectou = True
                        self.status_signal.emit("Câmera conectada")
                        break
                    cap.release()

                if not reconectou and self._running:
                    self.status_signal.emit(
                        "Falha ao reconectar à câmera configurada."
                    )
                continue

            inicio_inferencia = time.perf_counter()
            result = model(frame, conf=0.50, classes=[0], verbose=False)[0]
            inferencia_ms = (time.perf_counter() - inicio_inferencia) * 1000

            annotated_frame = result.plot()
            altura, largura = frame.shape[:2]

            zona = self._zona
            poligono = None
            if zona is not None:
                poligono = self._montar_poligono(zona, largura, altura)
                overlay = annotated_frame.copy()
                cv2.fillPoly(overlay, [poligono], (0, 0, 255))
                annotated_frame = cv2.addWeighted(
                    overlay, 0.12, annotated_frame, 0.88, 0
                )
                cv2.polylines(
                    annotated_frame,
                    [poligono],
                    isClosed=True,
                    color=(0, 0, 255),
                    thickness=3,
                )

            caixas = result.boxes.xyxy.cpu().numpy() if result.boxes is not None else []
            quantidade_pessoas = len(caixas)
            alerta = False

            for caixa in (caixas if poligono is not None else []):
                x1, y1, x2, y2 = caixa[:4]
                ponto_pe = (int((x1 + x2) / 2), int(y2))
                if cv2.pointPolygonTest(poligono, ponto_pe, False) >= 0:
                    alerta = True
                    cv2.circle(annotated_frame, ponto_pe, 7, (0, 0, 255), -1)

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

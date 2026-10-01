import sys
import os
import time

import cv2
import numpy as np
from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QSizePolicy,
    QFrame,
)
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtGui import QImage, QPixmap, QKeySequence
from PyQt5.QtWidgets import QShortcut
from ultralytics import YOLO

# Usa TCP para maior estabilidade em streams RTSP.
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"


class VideoThread(QThread):
    """Lê a câmera, detecta pessoas e verifica a zona monitorada."""

    frame_signal = pyqtSignal(QImage)
    status_signal = pyqtSignal(str)
    alert_signal = pyqtSignal(bool)
    metrics_signal = pyqtSignal(float, int, float)  # FPS, pessoas, inferência em ms

    def __init__(self, rtsp_url, model_path="yolov8n.pt"):
        super().__init__()
        self.rtsp_url = rtsp_url
        self.model_path = model_path
        self._running = True
        self._paused = False

    def run(self):
        self.status_signal.emit("Carregando modelo...")
        try:
            model = YOLO(self.model_path)
        except Exception as e:
            self.status_signal.emit(f"Erro ao carregar modelo: {e}")
            return

        self.status_signal.emit("Conectando à câmera...")
        cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
        if not cap.isOpened():
            self.status_signal.emit(
                "Falha na conexão RTSP. Confira câmera, IP e endereço do stream."
            )
            cap.release()
            return

        self.status_signal.emit("Câmera conectada")
        ultimo_alerta = None
        ultimo_tempo_fps = time.perf_counter()
        quadros_no_intervalo = 0
        fps_atual = 0.0

        # Polígono central expresso em proporções do quadro.
        pontos_relativos = [
            (0.35, 0.30),
            (0.65, 0.30),
            (0.65, 0.75),
            (0.35, 0.75),
        ]

        while self._running:
            if self._paused:
                self.msleep(100)
                continue

            ret, frame = cap.read()
            if not ret:
                self.status_signal.emit("Sinal perdido. Tentando reconectar...")
                cap.release()
                self.msleep(1000)
                if self._running:
                    cap.open(self.rtsp_url, cv2.CAP_FFMPEG)
                    if cap.isOpened():
                        self.status_signal.emit("Câmera reconectada")
                continue

            inicio_inferencia = time.perf_counter()
            result = model(frame, conf=0.50, classes=[0], verbose=False)[0]
            inferencia_ms = (time.perf_counter() - inicio_inferencia) * 1000
            annotated_frame = result.plot()

            altura, largura = frame.shape[:2]
            poligono = np.array(
                [
                    (int(x * largura), int(y * altura))
                    for x, y in pontos_relativos
                ],
                dtype=np.int32,
            ).reshape((-1, 1, 2))

            # Região monitorada em vermelho translúcido.
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
            cv2.putText(
                annotated_frame,
                "ZONA MONITORADA",
                (int(0.35 * largura), max(30, int(0.30 * altura) - 10)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.75,
                (0, 0, 255),
                2,
                cv2.LINE_AA,
            )

            # Usa o centro inferior da caixa como estimativa da posição dos pés.
            caixas = result.boxes.xyxy.cpu().numpy() if result.boxes is not None else []
            quantidade_pessoas = len(caixas)
            alerta = False
            for caixa in caixas:
                x1, y1, x2, y2 = caixa[:4]
                ponto_pe = (int((x1 + x2) / 2), int(y2))
                dentro = cv2.pointPolygonTest(poligono, ponto_pe, False) >= 0
                if dentro:
                    alerta = True
                    cv2.circle(annotated_frame, ponto_pe, 7, (0, 0, 255), -1)

            if alerta != ultimo_alerta:
                self.alert_signal.emit(alerta)
                ultimo_alerta = alerta

            # Atualiza o FPS em intervalos de aproximadamente um segundo.
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
            qt_image = QImage(
                rgb_image.data,
                w,
                h,
                ch * w,
                QImage.Format_RGB888,
            ).copy()
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


class JanelaVideoCheio(QWidget):
    """Janela separada para ampliar o vídeo sem os cartões da interface."""

    fechada = pyqtSignal()

    def __init__(self):
        super().__init__(None, Qt.Window)
        self.setWindowTitle("VIGIA | Vídeo ao vivo")
        self.setStyleSheet("background-color: #000000;")
        self.imagem_atual = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel("Aguardando vídeo...")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("background-color: #000000; color: #aab9cc;")
        layout.addWidget(self.label)

    def atualizar_imagem(self, pixmap):
        self.imagem_atual = pixmap
        self.redimensionar_imagem()

    def redimensionar_imagem(self):
        if self.imagem_atual is not None:
            self.label.setPixmap(
                self.imagem_atual.scaled(
                    self.label.size(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
            )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.redimensionar_imagem()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Escape, Qt.Key_F11):
            self.close()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        self.fechada.emit()
        event.accept()


class JanelaPrincipal(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VIGIA | Monitoramento Inteligente")
        self.resize(1280, 740)
        self.setMinimumSize(980, 620)

        # Configurações de ligação da câmera.
        self.SENHA_DISPOSITIVO = "MURUIA2026"
        self.IP_CAMERA = "192.168.0.110"
        self.RTSP_URL = (
            f"rtsp://admin:{self.SENHA_DISPOSITIVO}@{self.IP_CAMERA}:554/"
            "cam/realmonitor?channel=1&subtype=0"
        )

        self.model_path = "yolov8n.pt"
        self.video_thread = None
        self.ultima_imagem = None
        self.fullscreen_window = None

        self.init_ui()
        self.aplicar_tema()
        self.fullscreen_shortcut = QShortcut(QKeySequence("F11"), self)
        self.fullscreen_shortcut.activated.connect(self.alternar_tela_cheia)

    def init_ui(self):
        central = QWidget(self)
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        self.main_layout = layout
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # Cabeçalho do painel.
        header = QHBoxLayout()
        brand = QVBoxLayout()
        titulo = QLabel("VIGIA")
        self.titulo_label = titulo
        titulo.setObjectName("app_title")
        subtitulo = QLabel("MONITORAMENTO INTELIGENTE DE ÁREA")
        self.subtitulo_label = subtitulo
        subtitulo.setObjectName("app_subtitle")
        brand.addWidget(titulo)
        brand.addWidget(subtitulo)
        header.addLayout(brand)
        header.addStretch()

        self.camera_badge = QLabel("●  CÂMERA OFFLINE")
        self.camera_badge.setObjectName("badge_offline")
        self.analysis_badge = QLabel("ANÁLISE PARADA")
        self.analysis_badge.setObjectName("badge_idle")
        header.addWidget(self.camera_badge)
        header.addWidget(self.analysis_badge)
        self.header_items = [
            self.titulo_label,
            self.subtitulo_label,
            self.camera_badge,
            self.analysis_badge,
        ]
        layout.addLayout(header)

        # Área principal em duas colunas: vídeo 16:9 e painel lateral.
        body_layout = QHBoxLayout()
        body_layout.setSpacing(14)
        left_column = QWidget()
        self.left_column_layout = QVBoxLayout(left_column)
        self.left_column_layout.setContentsMargins(0, 0, 0, 0)
        self.left_column_layout.setSpacing(10)

        self.side_panel = QFrame()
        self.side_panel.setObjectName("side_panel")
        self.side_layout = QVBoxLayout(self.side_panel)
        self.side_layout.setContentsMargins(12, 12, 12, 12)
        self.side_layout.setSpacing(10)

        # Cartão do vídeo e seu cabeçalho.
        self.video_card = QFrame()
        self.video_card.setObjectName("video_card")
        video_card_layout = QVBoxLayout(self.video_card)
        video_card_layout.setContentsMargins(10, 8, 10, 10)
        video_card_layout.setSpacing(10)

        video_header = QHBoxLayout()
        video_heading = QLabel("VISUALIZAÇÃO AO VIVO")
        self.video_heading = video_heading
        video_heading.setObjectName("section_title")
        self.camera_address_label = QLabel(f"CÂMERA  •  {self.IP_CAMERA}")
        self.camera_address_label.setObjectName("muted_text")
        video_header.addWidget(video_heading)
        video_header.addStretch()
        video_header.addWidget(self.camera_address_label)
        self.video_header_items = [video_heading, self.camera_address_label]
        video_card_layout.addLayout(video_header)

        self.label_video = QLabel("Aguardando início da transmissão")
        self.label_video.setObjectName("video_display")
        self.label_video.setAlignment(Qt.AlignCenter)
        self.label_video.setMinimumHeight(390)
        self.label_video.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        video_card_layout.addWidget(self.label_video, stretch=1)

        self.alert_label = QLabel("ZONA SEGURA  •  NENHUMA PESSOA DETECTADA NA ÁREA")
        self.alert_label.setObjectName("alert_safe")
        self.alert_label.setAlignment(Qt.AlignCenter)
        self.alert_label.setFixedHeight(42)
        self.left_column_layout.addWidget(self.video_card, stretch=1)
        # O estado do alerta fica fora do quadro da câmera, nunca sobre a imagem.
        self.left_column_layout.addWidget(self.alert_label)

        # Cartões de métricas.
        metrics = QVBoxLayout()
        metrics.setSpacing(12)
        self.metric_people = self.criar_cartao_metrica("PESSOAS", "—", "na imagem")
        self.metric_fps = self.criar_cartao_metrica("FLUIDEZ", "—", "quadros / s")
        self.metric_latency = self.criar_cartao_metrica("INFERÊNCIA", "—", "milissegundos")
        self.metric_model = self.criar_cartao_metrica("MODELO", "YOLOv8n", "classe: pessoa")
        self.metric_cards = [
            self.metric_people,
            self.metric_fps,
            self.metric_latency,
            self.metric_model,
        ]
        for card in (
            self.metric_people,
            self.metric_fps,
            self.metric_latency,
            self.metric_model,
        ):
            metrics.addWidget(card, stretch=1)
        self.side_layout.addLayout(metrics)

        # Barra de controles.
        controls = QVBoxLayout()
        controls.setSpacing(10)
        self.status_label = QLabel("Pronto para iniciar")
        self.status_label.setObjectName("footer_status")
        self.status_label.setWordWrap(True)
        controls.addWidget(self.status_label)

        self.btn_iniciar = QPushButton("INICIAR MONITORAMENTO")
        self.btn_iniciar.setObjectName("btn_primary")
        self.btn_pausar = QPushButton("PAUSAR")
        self.btn_pausar.setObjectName("btn_secondary")
        self.btn_reativar = QPushButton("REATIVAR")
        self.btn_reativar.setObjectName("btn_secondary")
        self.btn_fullscreen = QPushButton("TELA CHEIA  F11")
        self.btn_fullscreen.setObjectName("btn_ghost")

        self.btn_pausar.setEnabled(False)
        self.btn_reativar.setEnabled(False)
        self.btn_iniciar.clicked.connect(self.iniciar_stream)
        self.btn_pausar.clicked.connect(self.pausar_stream)
        self.btn_reativar.clicked.connect(self.despausar_stream)
        self.btn_fullscreen.clicked.connect(self.alternar_tela_cheia)

        controls.addWidget(self.btn_iniciar)
        controls.addWidget(self.btn_pausar)
        controls.addWidget(self.btn_reativar)
        controls.addWidget(self.btn_fullscreen)
        self.control_items = [
            self.status_label,
            self.btn_iniciar,
            self.btn_pausar,
            self.btn_reativar,
            self.btn_fullscreen,
        ]
        self.side_layout.addLayout(controls)
        self.side_layout.addStretch()
        body_layout.addWidget(left_column, stretch=4)
        body_layout.addWidget(self.side_panel, stretch=1)
        layout.addLayout(body_layout, stretch=1)

    def criar_cartao_metrica(self, titulo, valor, descricao):
        card = QFrame()
        card.setObjectName("metric_card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 10, 14, 10)
        card_layout.setSpacing(2)

        label_titulo = QLabel(titulo)
        label_titulo.setObjectName("metric_title")
        label_valor = QLabel(valor)
        label_valor.setObjectName("metric_value")
        label_descricao = QLabel(descricao)
        label_descricao.setObjectName("metric_description")

        card_layout.addWidget(label_titulo)
        card_layout.addWidget(label_valor)
        card_layout.addWidget(label_descricao)
        card.valor_label = label_valor
        return card

    def aplicar_tema(self):
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #0b1220;
                color: #e5edf7;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QLabel#app_title {
                color: #f8fafc;
                font-size: 27px;
                font-weight: 800;
                letter-spacing: 2px;
            }
            QLabel#app_subtitle {
                color: #7f91a8;
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 1.5px;
            }
            QLabel#badge_offline, QLabel#badge_online,
            QLabel#badge_idle, QLabel#badge_running, QLabel#badge_paused {
                padding: 9px 13px;
                border-radius: 8px;
                font-size: 11px;
                font-weight: 700;
            }
            QLabel#badge_offline { background-color: #33212a; color: #fda4af; }
            QLabel#badge_online { background-color: #12352d; color: #6ee7b7; }
            QLabel#badge_idle { background-color: #1c293a; color: #aab9cc; }
            QLabel#badge_running { background-color: #12352d; color: #6ee7b7; }
            QLabel#badge_paused { background-color: #3a2d17; color: #fcd34d; }
            QFrame#video_card, QFrame#metric_card {
                background-color: #111c2d;
                border: 1px solid #233248;
                border-radius: 12px;
            }
            QFrame#side_panel {
                background-color: #0e1827;
                border: 1px solid #233248;
                border-radius: 12px;
            }
            QLabel#section_title {
                color: #dce7f5;
                font-size: 12px;
                font-weight: 800;
                letter-spacing: 1px;
            }
            QLabel#muted_text {
                color: #8293a9;
                font-size: 11px;
            }
            QLabel#video_display {
                background-color: #050a12;
                border: 1px solid #1d2a3d;
                border-radius: 8px;
                color: #6e8096;
                font-size: 15px;
            }
            QLabel#alert_safe, QLabel#alert_active {
                border-radius: 8px;
                font-size: 12px;
                font-weight: 800;
                letter-spacing: 0.5px;
            }
            QLabel#alert_safe { background-color: #12352d; color: #6ee7b7; }
            QLabel#alert_active { background-color: #8f2028; color: #fff1f2; }
            QLabel#metric_title {
                color: #8293a9;
                font-size: 10px;
                font-weight: 800;
                letter-spacing: 1px;
            }
            QLabel#metric_value {
                color: #f8fafc;
                font-size: 22px;
                font-weight: 800;
            }
            QLabel#metric_description {
                color: #71839a;
                font-size: 10px;
            }
            QLabel#footer_status {
                color: #91a2b8;
                font-size: 11px;
            }
            QPushButton {
                min-height: 40px;
                padding: 0 14px;
                border-radius: 8px;
                font-size: 11px;
                font-weight: 800;
            }
            QPushButton#btn_primary {
                background-color: #0e8f70;
                color: white;
                border: none;
            }
            QPushButton#btn_primary:hover { background-color: #10a37e; }
            QPushButton#btn_primary:disabled {
                background-color: #26394a;
                color: #8090a2;
            }
            QPushButton#btn_secondary {
                background-color: #1b293b;
                color: #dce7f5;
                border: 1px solid #30435b;
            }
            QPushButton#btn_secondary:hover:enabled { background-color: #26384e; }
            QPushButton#btn_secondary:disabled {
                color: #596a7d;
                border-color: #263243;
            }
            QPushButton#btn_ghost {
                background-color: transparent;
                color: #91a2b8;
                border: 1px solid #304056;
            }
            QPushButton#btn_ghost:hover { background-color: #172337; color: #e5edf7; }
        """)

    def iniciar_stream(self):
        if self.video_thread is not None and self.video_thread.isRunning():
            return

        self.alerta_visual(False)
        self.camera_badge.setText("●  CONECTANDO CÂMERA")
        self.camera_badge.setObjectName("badge_offline")
        self.camera_badge.style().unpolish(self.camera_badge)
        self.camera_badge.style().polish(self.camera_badge)
        self.analysis_badge.setText("ANÁLISE INICIANDO")
        self.analysis_badge.setObjectName("badge_idle")
        self.analysis_badge.style().unpolish(self.analysis_badge)
        self.analysis_badge.style().polish(self.analysis_badge)
        self.status_label.setText("Carregando modelo e conectando à câmera...")
        self.btn_iniciar.setEnabled(False)
        self.btn_pausar.setEnabled(True)
        self.btn_reativar.setEnabled(False)

        self.video_thread = VideoThread(self.RTSP_URL, model_path=self.model_path)
        self.video_thread.frame_signal.connect(self.atualizar_frame)
        self.video_thread.status_signal.connect(self.atualizar_status)
        self.video_thread.alert_signal.connect(self.alerta_visual)
        self.video_thread.metrics_signal.connect(self.atualizar_metricas)
        self.video_thread.finished.connect(self.thread_finalizada)
        self.video_thread.start()

    def pausar_stream(self):
        if self.video_thread and self.video_thread.isRunning():
            self.video_thread.pause()
            self.btn_pausar.setEnabled(False)
            self.btn_reativar.setEnabled(True)
            self.analysis_badge.setText("ANÁLISE PAUSADA")
            self.analysis_badge.setObjectName("badge_paused")
            self.analysis_badge.style().unpolish(self.analysis_badge)
            self.analysis_badge.style().polish(self.analysis_badge)
            self.status_label.setText("Monitoramento pausado pelo operador")

    def despausar_stream(self):
        if self.video_thread and self.video_thread.isRunning():
            self.video_thread.resume()
            self.btn_pausar.setEnabled(True)
            self.btn_reativar.setEnabled(False)
            self.analysis_badge.setText("ANÁLISE ATIVA")
            self.analysis_badge.setObjectName("badge_running")
            self.analysis_badge.style().unpolish(self.analysis_badge)
            self.analysis_badge.style().polish(self.analysis_badge)
            self.status_label.setText("Monitoramento ativo")

    def atualizar_frame(self, imagem):
        self.ultima_imagem = QPixmap.fromImage(imagem)
        self.redimensionar_imagem()
        if self.fullscreen_window and self.fullscreen_window.isVisible():
            self.fullscreen_window.atualizar_imagem(self.ultima_imagem)

    def redimensionar_imagem(self):
        if self.ultima_imagem is not None:
            # Exibe o quadro completo, sem corte nem distorção.
            self.label_video.setPixmap(
                self.ultima_imagem.scaled(
                    self.label_video.size(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
            )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.redimensionar_imagem()

    def atualizar_status(self, mensagem):
        self.status_label.setText(mensagem)
        if "Câmera conectada" in mensagem or "Câmera reconectada" in mensagem:
            self.camera_badge.setText("●  CÂMERA ONLINE")
            self.camera_badge.setObjectName("badge_online")
            self.camera_badge.style().unpolish(self.camera_badge)
            self.camera_badge.style().polish(self.camera_badge)
            self.analysis_badge.setText("ANÁLISE ATIVA")
            self.analysis_badge.setObjectName("badge_running")
            self.analysis_badge.style().unpolish(self.analysis_badge)
            self.analysis_badge.style().polish(self.analysis_badge)
        elif "Falha na conexão" in mensagem or "Sinal perdido" in mensagem:
            self.camera_badge.setText("●  CÂMERA OFFLINE")
            self.camera_badge.setObjectName("badge_offline")
            self.camera_badge.style().unpolish(self.camera_badge)
            self.camera_badge.style().polish(self.camera_badge)

    def atualizar_metricas(self, fps, pessoas, inferencia_ms):
        self.metric_people.valor_label.setText(str(pessoas))
        self.metric_fps.valor_label.setText(f"{fps:.1f}")
        self.metric_latency.valor_label.setText(f"{inferencia_ms:.0f} ms")

    def alerta_visual(self, ativo):
        if ativo:
            self.alert_label.setText("ALERTA  •  PESSOA DETECTADA NA ZONA MONITORADA")
            self.alert_label.setObjectName("alert_active")
        else:
            self.alert_label.setText("ZONA SEGURA  •  NENHUMA PESSOA DETECTADA NA ÁREA")
            self.alert_label.setObjectName("alert_safe")
        self.alert_label.style().unpolish(self.alert_label)
        self.alert_label.style().polish(self.alert_label)

    def thread_finalizada(self):
        self.btn_iniciar.setEnabled(True)
        self.btn_pausar.setEnabled(False)
        self.btn_reativar.setEnabled(False)
        self.analysis_badge.setText("ANÁLISE PARADA")
        self.analysis_badge.setObjectName("badge_idle")
        self.analysis_badge.style().unpolish(self.analysis_badge)
        self.analysis_badge.style().polish(self.analysis_badge)
        if self.video_thread and not self.video_thread.isRunning():
            if "Câmera conectada" not in self.status_label.text():
                self.camera_badge.setText("●  CÂMERA OFFLINE")
                self.camera_badge.setObjectName("badge_offline")
                self.camera_badge.style().unpolish(self.camera_badge)
                self.camera_badge.style().polish(self.camera_badge)

    def alternar_tela_cheia(self):
        if self.fullscreen_window and self.fullscreen_window.isVisible():
            self.fullscreen_window.close()
            return

        self.fullscreen_window = JanelaVideoCheio()
        self.fullscreen_window.fechada.connect(self.limpar_janela_tela_cheia)
        if self.ultima_imagem is not None:
            self.fullscreen_window.atualizar_imagem(self.ultima_imagem)
        self.fullscreen_window.showFullScreen()

    def limpar_janela_tela_cheia(self):
        self.fullscreen_window = None

    def closeEvent(self, event):
        if self.fullscreen_window:
            self.fullscreen_window.close()
        if self.video_thread and self.video_thread.isRunning():
            self.video_thread.stop()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    janela = JanelaPrincipal()
    janela.show()
    sys.exit(app.exec_())

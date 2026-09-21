import sys
import os
import cv2
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QSizePolicy, QFrame
)
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtGui import QImage, QPixmap
from ultralytics import YOLO

# Configuração de transporte TCP para otimizar streams RTSP
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"


class VideoThread(QThread):
    """Thread dedicada à leitura da câmara e processamento da IA."""
    frame_signal = pyqtSignal(QImage)
    status_signal = pyqtSignal(str)

    def __init__(self, rtsp_url, model_path="yolov8n.pt"):
        super().__init__()
        self.rtsp_url = rtsp_url
        self.model_path = model_path
        self._running = True
        self._paused = False

    def run(self):
        # -----------------------------------------------------------------------------------
        # [LINHA PARA EDITAR O MODELO FUTURE]
        # Quando tiveres o teu modelo treinado no CVAT (ex: coletes.pt), altera aqui:
        self.status_signal.emit("Carregando modelo de IA...")
        try:
            model = YOLO(self.model_path)
        except Exception as e:
            self.status_signal.emit(f"Erro ao carregar modelo: {e}")
            return
        # -----------------------------------------------------------------------------------

        self.status_signal.emit("Lançando conexão com a câmara...")
        cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)

        if not cap.isOpened():
            self.status_signal.emit("Erro crítico: Câmera offline ou IP incorreto.")
            return

        self.status_signal.emit("Câmera conectada com sucesso!")

        while self._running:
            if self._paused:
                self.msleep(100)
                continue

            ret, frame = cap.read()
            if not ret:
                self.status_signal.emit("Sinal perdido. Tentando reconectar...")
                self.msleep(1000)
                # Tenta reabrir a captura
                cap.open(self.rtsp_url, cv2.CAP_FFMPEG)
                continue

            # Processamento da imagem pelo YOLO (podes ajustar 'conf' para sensibilidade)
            results = model(frame, conf=0.5, verbose=False)
            annotated_frame = results[0].plot()

            # Conversão de BGR para RGB para exibir no PyQt5
            rgb_image = cv2.cvtColor(annotated_frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb_image.shape
            bytes_per_line = ch * w
            qt_image = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888)

            self.frame_signal.emit(qt_image)

        cap.release()
        self.status_signal.emit("Transmissão encerrada.")

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    def stop(self):
        self._running = False
        self.wait()


class JanelaPrincipal(QMainWindow):
    def __init__(self):
        super().__init__()

        # -----------------------------------------------------------------------------------
        # [LINHA PARA EDITAR O TÍTULO DA JANELA]
        self.setWindowTitle("Monitorização e Deteção de EPI 1.0 - TCC [cite: Seu Nome]")
        # -----------------------------------------------------------------------------------
        
        self.resize(1100, 750)

        # Configurações de Ligação da Câmara
        self.SENHA_DISPOSITIVO = "MURUIA2026"
        self.IP_CAMERA = "192.168.0.111"
        self.RTSP_URL = f"rtsp://admin:{self.SENHA_DISPOSITIVO}@{self.IP_CAMERA}:554/cam/realmonitor?channel=1&subtype=0"

        # Definir o caminho do modelo (começamos com o padrão)
        self.model_path = "yolov8n.pt" 
        self.video_thread = None

        # Construção da Interface
        self.init_ui()
        self.aplicar_tema_escuro()

    def init_ui(self):
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        # Contonêr do Vídeo para dar uma borda profissional
        video_frame = QFrame(self)
        video_frame.setObjectName("video_frame")
        video_layout = QVBoxLayout(video_frame)
        video_layout.setContentsMargins(5, 5, 5, 5)

        # -----------------------------------------------------------------------------------
        # [LINHA PARA EDITAR O TEXTO INICIAL NO QUADRO DE VÍDEO]
        self.label_video = QLabel("Aguardando transmissão ser iniciada...", self)
        # -----------------------------------------------------------------------------------
        
        self.label_video.setAlignment(Qt.AlignCenter)
        
        # [CORREÇÃO PROFISSIONAL]: Garantir que a proporção seja mantida
        self.label_video.setScaledContents(False) 
        self.label_video.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        video_layout.addWidget(self.label_video)

        # Area de Status Visual
        status_layout = QHBoxLayout()
        label_static_status = QLabel("Status:", self)
        label_static_status.setStyleSheet("font-weight: bold; color: #94a3b8; font-size: 14px;")
        
        # -----------------------------------------------------------------------------------
        # [LINHA PARA EDITAR O TEXTO INICIAL DO STATUS]
        self.status_label = QLabel("Sistema Pronto.", self)
        # -----------------------------------------------------------------------------------
        self.status_label.setObjectName("status_label")
        
        status_layout.addWidget(label_static_status)
        status_layout.addWidget(self.status_label)
        status_layout.addStretch() # Empurra o status para a esquerda

        # Layout dos Botões (Horizontal na base)
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(15)

        # -----------------------------------------------------------------------------------
        # [LINHAS PARA EDITAR OS NOMES DOS BOTÕES]
        self.btn_iniciar = QPushButton("INICIAR CÂMERA", self)
        self.btn_pausar = QPushButton("PAUSAR", self)
        self.btn_despausar = QPushButton("REAVIVAR", self)
        # -----------------------------------------------------------------------------------

        # Estilo fixo para os botões
        for btn in (self.btn_iniciar, self.btn_pausar, self.btn_despausar):
            btn.setFixedHeight(50)
            btn.setCursor(Qt.PointingHandCursor)

        buttons_layout.addWidget(self.btn_iniciar)
        buttons_layout.addWidget(self.btn_pausar)
        buttons_layout.addWidget(self.btn_despausar)

        # Adicionar tudo ao layout principal
        main_layout.addWidget(video_frame, stretch=1)
        main_layout.addLayout(status_layout)
        main_layout.addLayout(buttons_layout)

        central_widget.setLayout(main_layout)

        # Ligar os cliques
        self.btn_iniciar.clicked.connect(self.iniciar_stream)
        self.btn_pausar.clicked.connect(self.pausar_stream)
        self.btn_despausar.clicked.connect(self.despausar_stream)

    def aplicar_tema_escuro(self):
        """Estilização visual moderna refinada."""
        qss = """
            QMainWindow {
                background-color: #020617;
            }
            QFrame#video_frame {
                border: 2px solid #1e293b;
                background-color: #000000;
                border-radius: 10px;
            }
            QLabel {
                color: #f8fafc;
                font-family: 'Segoe UI', sans-serif;
                font-size: 16px;
                background: transparent;
            }
            QLabel#status_label {
                color: #38bdf8; /* Azul claro para o status */
                font-weight: 600;
                font-size: 14px;
            }
            QPushButton {
                background-color: #1e293b;
                color: #f8fafc;
                border: 1px solid #334155;
                border-radius: 8px;
                font-weight: 700;
                font-size: 15px;
                text-transform: uppercase;
            }
            QPushButton:hover {
                background-color: #334155;
            }
            QPushButton:pressed {
                background-color: #0f172a;
            }
            QPushButton#btn_iniciar {
                background-color: #16a34a; /* Verde */
                border: none;
            }
            QPushButton#btn_iniciar:hover {
                background-color: #15803d;
            }
        """
        self.setStyleSheet(qss)
        self.btn_iniciar.setObjectName("btn_iniciar")

    def iniciar_stream(self):
        if self.video_thread is None or not self.video_thread.isRunning():
            self.video_thread = VideoThread(self.RTSP_URL, model_path=self.model_path)
            self.video_thread.frame_signal.connect(self.atualizar_frame)
            self.video_thread.status_signal.connect(self.atualizar_status)
            self.video_thread.start()

    def pausar_stream(self):
        if self.video_thread:
            self.video_thread.pause()

    def despausar_stream(self):
        if self.video_thread:
            self.video_thread.resume()

    def atualizar_frame(self, qt_image):
        # [MÉTODO PROFISSIONAL]: Mantém a proporção e adiciona bordas pretas
        # se o tamanho da janela mudar.
        pixmap = QPixmap.fromImage(qt_image)
        scaled_pixmap = pixmap.scaled(
            self.label_video.size(), 
            Qt.KeepAspectRatio, 
            Qt.SmoothTransformation
        )
        self.label_video.setPixmap(scaled_pixmap)

    def atualizar_status(self, mensagem):
        # Atualiza o status na própria interface gráfica
        self.status_label.setText(mensagem)

    def closeEvent(self, event):
        if self.video_thread:
            self.video_thread.stop()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    janela = JanelaPrincipal()
    janela.show()
    sys.exit(app.exec_())
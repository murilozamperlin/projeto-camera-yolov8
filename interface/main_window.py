import json
import math
import os
from pathlib import Path
from collections import deque
from datetime import datetime

from PyQt5.QtCore import Qt, QTimer, QRect, QPointF, pyqtSignal
from PyQt5.QtGui import (
    QPixmap, QKeySequence, QPainter, QPen, QColor, QPolygonF, QBrush
)
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QSizePolicy, QFrame, QShortcut, QSlider, QCheckBox, QDoubleSpinBox, QSpinBox,
    QListWidget, QScrollArea, QDialog, QDialogButtonBox, QFormLayout, QPlainTextEdit,
    QGridLayout, QMessageBox, QTabWidget, QLineEdit, QInputDialog,
)
from interface.video_thread import VideoThread


class JanelaVideoCheio(QWidget):
    def __init__(self):
        super().__init__(None, Qt.Window)
        self.setWindowTitle("VIGIA | Vídeo ao vivo")
        self.setStyleSheet("background-color: #000000;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel("Aguardando vídeo...")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("background-color: #000000; color: #94a3b8;")
        layout.addWidget(self.label)

    def atualizar_imagem(self, pixmap):
        if pixmap is not None:
            self.label.setPixmap(
                pixmap.scaled(self.label.size(), Qt.KeepAspectRatio,
                              Qt.SmoothTransformation)
            )

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Escape, Qt.Key_F11):
            self.close()


class GraficoFPS(QWidget):
    def __init__(self, maximo_pontos=60):
        super().__init__()
        self.valores = deque(maxlen=maximo_pontos)
        self.setMinimumHeight(90)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def adicionar(self, valor):
        self.valores.append(valor)
        self.update()

    def limpar(self):
        self.valores.clear()
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.rect().adjusted(0, 4, 0, -4)
        p.fillRect(self.rect(), QColor("#f8fafc"))

        p.setPen(QPen(QColor("#e2e8f0"), 1))
        for i in range(4):
            y = r.top() + i * r.height() / 3
            p.drawLine(r.left(), int(y), r.right(), int(y))

        if len(self.valores) < 2:
            p.setPen(QColor("#94a3b8"))
            p.drawText(self.rect(), Qt.AlignCenter, "sem dados")
            return

        topo = max(30.0, max(self.valores) * 1.15)
        n = len(self.valores)
        passo = r.width() / (self.valores.maxlen - 1)
        x0 = r.right() - (n - 1) * passo
        pts = [
            QPointF(x0 + i * passo, r.bottom() - (v / topo) * r.height())
            for i, v in enumerate(self.valores)
        ]

        area = QPolygonF(pts + [QPointF(pts[-1].x(), r.bottom()),
                                QPointF(pts[0].x(), r.bottom())])
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(37, 99, 235, 35)))
        p.drawPolygon(area)

        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor("#2563eb"), 2))
        p.drawPolyline(QPolygonF(pts))

        p.setPen(QColor("#94a3b8"))
        p.drawText(r.left() + 4, r.top() + 11, f"{topo:.0f}")


class VideoLabel(QLabel):
    poligono_finalizado = pyqtSignal(object)
    retangulo_finalizado = pyqtSignal(object, object)

    def __init__(self, texto=""):
        super().__init__(texto)
        self.modo_desenho = False
        self.tipo_desenho = "poligono"
        self._vertices_rascunho = []
        self._inicio_arraste = None
        self._fim_arraste = None

    def definir_modo_desenho(self, ativo, tipo="poligono"):
        self.modo_desenho = ativo
        self.tipo_desenho = tipo
        self._vertices_rascunho = []
        self._inicio_arraste = None
        self._fim_arraste = None
        self.setCursor(Qt.CrossCursor if ativo else Qt.ArrowCursor)
        self.update()

    def retangulo_pixmap(self):
        pm = self.pixmap()
        if pm is None or pm.isNull():
            return None
        x = (self.width() - pm.width()) // 2
        y = (self.height() - pm.height()) // 2
        return QRect(x, y, pm.width(), pm.height())

    def mousePressEvent(self, e):
        if not self.modo_desenho:
            return super().mousePressEvent(e)

        if e.button() == Qt.LeftButton:
            rect = self.retangulo_pixmap()
            if rect is None or not rect.contains(e.pos()):
                return
            if self.tipo_desenho == "retangulo":
                self._inicio_arraste = e.pos()
                self._fim_arraste = e.pos()
                self.update()
                e.accept()
                return
            self._vertices_rascunho.append(e.pos())
            self.update()
            e.accept()
            return

        if e.button() == Qt.RightButton:
            self.finalizar_desenho()
            e.accept()
            return

        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self.tipo_desenho == "retangulo" and self._inicio_arraste is not None:
            self._fim_arraste = e.pos()
            self.update()
            e.accept()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if (self.modo_desenho and self.tipo_desenho == "retangulo" and
                self._inicio_arraste is not None and e.button() == Qt.LeftButton):
            inicio, fim = self._inicio_arraste, e.pos()
            self._inicio_arraste = self._fim_arraste = None
            self.update()
            self.retangulo_finalizado.emit(inicio, fim)
            e.accept()
            return
        super().mouseReleaseEvent(e)

    def finalizar_desenho(self):
        if len(self._vertices_rascunho) < 3:
            return
        pontos = [(p.x(), p.y()) for p in self._vertices_rascunho]
        self._vertices_rascunho = []
        self.update()
        self.poligono_finalizado.emit(pontos)

    def paintEvent(self, e):
        super().paintEvent(e)
        if self._inicio_arraste is not None and self._fim_arraste is not None:
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            r = QRect(self._inicio_arraste, self._fim_arraste).normalized()
            p.setPen(QPen(QColor("#f59e0b"), 2, Qt.DashLine))
            p.setBrush(QBrush(QColor(220, 38, 38, 50)))
            p.drawRect(r)
            p.end()
            return
        if not self._vertices_rascunho:
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pontos = [QPointF(v) for v in self._vertices_rascunho]
        p.setPen(QPen(QColor("#f59e0b"), 2, Qt.DashLine))
        p.setBrush(QBrush(QColor(220, 38, 38, 45)))
        if len(pontos) >= 3:
            p.drawPolygon(QPolygonF(pontos))
        elif len(pontos) == 2:
            p.drawLine(pontos[0], pontos[1])
        for i, ponto in enumerate(pontos, start=1):
            p.setBrush(QBrush(QColor("#f59e0b")))
            p.drawEllipse(ponto, 5, 5)
            p.setPen(QPen(QColor("#ffffff"), 1))
            p.drawText(int(ponto.x()) + 6, int(ponto.y()) - 6, str(i))
            p.setPen(QPen(QColor("#f59e0b"), 2, Qt.DashLine))
        p.end()


class DialogoCalibracao(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Calibrar por referência")
        form = QFormLayout(self)

        self.real_mm = QDoubleSpinBox()
        self.real_mm.setRange(0.1, 100000)
        self.real_mm.setDecimals(1)
        self.real_mm.setSuffix(" mm")
        self.real_mm.setValue(1000)

        self.pixels = QDoubleSpinBox()
        self.pixels.setRange(1, 100000)
        self.pixels.setDecimals(0)
        self.pixels.setSuffix(" px")
        self.pixels.setValue(500)

        form.addRow("Comprimento real do objeto:", self.real_mm)
        form.addRow("Comprimento medido na imagem:", self.pixels)

        botoes = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)
        form.addRow(botoes)

    def fator_mm_por_px(self):
        return self.real_mm.value() / self.pixels.value()


class MainWindow(QMainWindow):
    PASTA_CAPTURAS = "capturas"
    SENHA_ZONA = "MURUIA"

    def __init__(self):
        super().__init__()
        self.setWindowTitle("VIGIA | Monitoramento Inteligente")
        self.resize(1440, 840)
        self.setMinimumSize(1100, 680)

        # A interface lê os valores locais; credenciais não ficam no código-fonte.
        self.ROOT_DIR = Path(__file__).resolve().parent.parent
        self.CONFIG_PATH = self.ROOT_DIR / "config.json"
        self.ZONA_PATH = self.ROOT_DIR / "zona_perigo.json"
        self.PASTA_CAPTURAS = str(self.ROOT_DIR / "capturas")
        try:
            config = json.loads(self.CONFIG_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            config = {}

        fonte = config.get("camera_source", "")
        self.CAMERA_SOURCE = fonte.strip() if isinstance(fonte, str) else fonte
        modelo = Path(str(config.get("model_path", "yolo26n.pt")))
        self.MODEL_PATH = str(modelo if modelo.is_absolute() else self.ROOT_DIR / modelo)

        self.video_thread = None
        self.ultima_imagem = None
        self.fullscreen_window = None

        self.zona_em_alerta = False
        self.total_alertas = 0
        self.total_capturas = 0
        self.inicio_sessao = None
        self.zona_edicao_liberada = False
        self.z_min_m = 0.0
        self.z_max_m = 2.0
        self.zona = self.carregar_zona()

        self.init_ui()
        self.aplicar_tema()
        self._sincronizar_campos_zona()
        self._atualizar_estado_edicao_zona()
        self.atualizar_info_zona()

        self.timer_sessao = QTimer(self)
        self.timer_sessao.timeout.connect(self.atualizar_tempo_sessao)

        QShortcut(QKeySequence("F11"), self).activated.connect(self.alternar_tela_cheia)
        QShortcut(QKeySequence("Ctrl+S"), self).activated.connect(self.capturar_imagem)

    def criar_card(self, titulo):
        card = QFrame()
        card.setObjectName("card")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(14, 12, 14, 14)
        lay.setSpacing(8)
        lbl = QLabel(titulo.upper())
        lbl.setObjectName("card_title")
        lay.addWidget(lbl)
        return card, lay

    def criar_linha_info(self, rotulo, valor="—"):
        linha = QHBoxLayout()
        a = QLabel(rotulo)
        a.setObjectName("info_key")
        b = QLabel(valor)
        b.setObjectName("info_value")
        b.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        linha.addWidget(a)
        linha.addStretch()
        linha.addWidget(b)
        return linha, b

    def criar_slider(self, minimo, maximo, valor, callback):
        s = QSlider(Qt.Horizontal)
        s.setRange(minimo, maximo)
        s.setValue(valor)
        s.valueChanged.connect(callback)
        return s

    def criar_pagina_rolavel(self):
        scroll = QScrollArea()
        scroll.setObjectName("control_scroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        conteudo = QWidget()
        conteudo.setObjectName("control_page")
        conteudo.setMinimumWidth(0)
        layout = QVBoxLayout(conteudo)
        layout.setContentsMargins(4, 6, 6, 8)
        layout.setSpacing(10)
        scroll.setWidget(conteudo)
        return scroll, layout

    def init_ui(self):
        central = QWidget(self)
        self.setCentralWidget(central)
        raiz = QVBoxLayout(central)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)

        raiz.addWidget(self.criar_cabecalho())

        corpo = QHBoxLayout()
        corpo.setContentsMargins(16, 16, 16, 16)
        corpo.setSpacing(16)
        corpo.addWidget(self.criar_painel_controle())
        corpo.addWidget(self.criar_area_video(), stretch=1)
        corpo.addWidget(self.criar_painel_status())
        raiz.addLayout(corpo, stretch=1)

        raiz.addWidget(self.criar_rodape())

    def criar_cabecalho(self):
        barra = QFrame()
        barra.setObjectName("header")
        barra.setFixedHeight(64)
        lay = QHBoxLayout(barra)
        lay.setContentsMargins(24, 0, 24, 0)

        marca = QVBoxLayout()
        marca.setSpacing(0)
        titulo = QLabel("VIGIA")
        titulo.setObjectName("app_title")
        sub = QLabel("Monitoramento inteligente de área")
        sub.setObjectName("app_subtitle")
        marca.addStretch()
        marca.addWidget(titulo)
        marca.addWidget(sub)
        marca.addStretch()
        lay.addLayout(marca)
        lay.addStretch()

        self.camera_badge = QLabel("● CÂMERA OFFLINE")
        self.analysis_badge = QLabel("ANÁLISE PARADA")
        self.definir_badge(self.camera_badge, "● CÂMERA OFFLINE", "danger")
        self.definir_badge(self.analysis_badge, "ANÁLISE PARADA", "neutral")
        lay.addWidget(self.camera_badge)
        lay.addSpacing(8)
        lay.addWidget(self.analysis_badge)
        return barra

    def criar_painel_controle(self):
        tabs = QTabWidget()
        tabs.setObjectName("control_tabs")
        tabs.setFixedWidth(300)
        tabs.setDocumentMode(True)
        tabs.tabBar().setExpanding(True)
        tabs.tabBar().setUsesScrollButtons(False)

        # Aba 1: operação
        pagina, col = self.criar_pagina_rolavel()
        card, lay = self.criar_card("Operação")
        self.btn_iniciar = QPushButton("▶  Iniciar monitoramento")
        self.btn_iniciar.setObjectName("btn_primary")
        self.btn_pausar = QPushButton("Pausar")
        self.btn_reativar = QPushButton("Reativar")
        self.btn_parar = QPushButton("■  Parar")
        self.btn_pausar.setObjectName("btn_secondary")
        self.btn_reativar.setObjectName("btn_secondary")
        self.btn_parar.setObjectName("btn_danger")
        self.btn_pausar.setEnabled(False)
        self.btn_reativar.setEnabled(False)
        self.btn_parar.setEnabled(False)
        self.btn_iniciar.clicked.connect(self.iniciar_stream)
        self.btn_pausar.clicked.connect(self.pausar_stream)
        self.btn_reativar.clicked.connect(self.despausar_stream)
        self.btn_parar.clicked.connect(self.parar_stream)
        lay.addWidget(self.btn_iniciar)
        linha = QHBoxLayout()
        linha.addWidget(self.btn_pausar)
        linha.addWidget(self.btn_reativar)
        lay.addLayout(linha)
        lay.addWidget(self.btn_parar)
        col.addWidget(card)
        card, lay = self.criar_card("Instruções rápidas")
        dica = QLabel("Desenhe a área de risco na aba Zona.\n"
                      "Use F11 para tela cheia e Ctrl+S para capturar.")
        dica.setObjectName("info_key")
        dica.setWordWrap(True)
        lay.addWidget(dica)
        col.addWidget(card)
        col.addStretch()
        tabs.addTab(pagina, "Operação")

        # Aba 2: acesso protegido e edição da zona.
        pagina, col = self.criar_pagina_rolavel()
        card, lay = self.criar_card("Proteção da zona")
        self.btn_desbloquear_zona = QPushButton("🔒  Desbloquear edição")
        self.btn_desbloquear_zona.setObjectName("btn_secondary")
        self.btn_desbloquear_zona.clicked.connect(self.alternar_bloqueio_zona)
        self.lbl_estado_edicao = QLabel("Edição bloqueada")
        self.lbl_estado_edicao.setObjectName("info_key")
        self.lbl_estado_edicao.setWordWrap(True)
        lay.addWidget(self.lbl_estado_edicao)
        lay.addWidget(self.btn_desbloquear_zona)
        col.addWidget(card)

        card, lay = self.criar_card("Definir polígono de risco")
        self.btn_zona = QPushButton("✏  Polígono — marcar vértices")
        self.btn_zona.setObjectName("btn_secondary")
        self.btn_zona.setCheckable(True)
        self.btn_zona.setEnabled(False)
        self.btn_zona.setMinimumWidth(0)
        self.btn_zona.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_zona.toggled.connect(self.alternar_modo_desenho)
        lay.addWidget(self.btn_zona)

        self.btn_zona_retangulo = QPushButton("▭  Retângulo — arrastar")
        self.btn_zona_retangulo.setObjectName("btn_secondary")
        self.btn_zona_retangulo.setCheckable(True)
        self.btn_zona_retangulo.setEnabled(False)
        self.btn_zona_retangulo.setMinimumWidth(0)
        self.btn_zona_retangulo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_zona_retangulo.toggled.connect(self.alternar_modo_retangulo)
        lay.addWidget(self.btn_zona_retangulo)

        ajuda = QLabel(
            "Polígono: marque os vértices; botão direito conclui. "
            "Retângulo: arraste. X = % horizontal; Y = % vertical da imagem, não metros."
        )
        ajuda.setObjectName("info_key")
        ajuda.setWordWrap(True)
        lay.addWidget(ajuda)

        self.ed_vertices = QPlainTextEdit()
        self.ed_vertices.setMinimumHeight(105)
        self.ed_vertices.setMaximumHeight(135)
        self.ed_vertices.setMinimumWidth(0)
        self.ed_vertices.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.ed_vertices.setTabChangesFocus(True)
        self.ed_vertices.setPlaceholderText(
            "20, 30\n70, 30\n75, 80\n15, 75"
        )
        self.ed_vertices.setToolTip(
            "Um vértice por linha, no formato X,Y. Valores entre 0 e 100; origem no canto superior esquerdo."
        )
        lay.addWidget(QLabel("Editar vértices manualmente — X,Y (%)"))
        lay.addWidget(self.ed_vertices)

        self.btn_aplicar_coordenadas = QPushButton("Aplicar polígono")
        self.btn_aplicar_coordenadas.setObjectName("btn_primary")
        self.btn_aplicar_coordenadas.clicked.connect(self.aplicar_coordenadas_zona)
        self.btn_zona_excluir = QPushButton("🗑  Excluir zona")
        self.btn_zona_excluir.setObjectName("btn_danger")
        self.btn_zona_excluir.clicked.connect(self.excluir_zona)
        lay.addWidget(self.btn_aplicar_coordenadas)
        lay.addWidget(self.btn_zona_excluir)

        self.lbl_zona_info = QLabel("")
        self.lbl_zona_info.setObjectName("info_key")
        self.lbl_zona_info.setWordWrap(True)
        lay.addWidget(self.lbl_zona_info)
        col.addWidget(card)

        card, lay = self.criar_card("Faixa Z — futuro")
        self.lbl_z_aviso = QLabel(
            "Estes limites Z descrevem uma faixa de altura da área/alvo acima do piso. "
            "Não são a altura de instalação da câmera: a distância da lente ao chão "
            "é um parâmetro separado. A câmera atual não mede profundidade, então "
            "esta faixa ainda não participa dos alertas."
        )
        self.lbl_z_aviso.setObjectName("z_warning")
        self.lbl_z_aviso.setWordWrap(True)
        lay.addWidget(self.lbl_z_aviso)

        grade_z = QGridLayout()
        grade_z.setHorizontalSpacing(8)
        grade_z.setVerticalSpacing(6)
        self.spin_z_min = QDoubleSpinBox()
        self.spin_z_max = QDoubleSpinBox()
        for campo in (self.spin_z_min, self.spin_z_max):
            campo.setRange(0.0, 20.0)
            campo.setDecimals(2)
            campo.setSingleStep(0.10)
            campo.setSuffix(" m")
        self.spin_z_min.setValue(self.z_min_m)
        self.spin_z_max.setValue(self.z_max_m)
        grade_z.addWidget(QLabel("Z mínimo"), 0, 0)
        grade_z.addWidget(self.spin_z_min, 0, 1)
        grade_z.addWidget(QLabel("Z máximo"), 1, 0)
        grade_z.addWidget(self.spin_z_max, 1, 1)
        lay.addLayout(grade_z)

        self.btn_salvar_faixa_z = QPushButton("Salvar limites Z")
        self.btn_salvar_faixa_z.setObjectName("btn_secondary")
        self.btn_salvar_faixa_z.clicked.connect(self.salvar_faixa_z)
        lay.addWidget(self.btn_salvar_faixa_z)
        col.addWidget(card)
        col.addStretch()
        tabs.addTab(pagina, "Zona")

        # Aba 3: preservar todos os controles de enquadramento e visualização.
        pagina, col = self.criar_pagina_rolavel()
        card, lay = self.criar_card("Alinhamento da câmera")
        self.chk_grade = QCheckBox("Grade 3×3")
        self.chk_mira = QCheckBox("Mira central")
        self.chk_grade.toggled.connect(self.renderizar)
        self.chk_mira.toggled.connect(self.renderizar)
        lay.addWidget(self.chk_grade)
        lay.addWidget(self.chk_mira)

        self.lbl_zoom = QLabel("Zoom digital: 1.0×")
        self.lbl_zoom.setObjectName("info_key")
        self.sld_zoom = self.criar_slider(100, 400, 100, self.mudou_zoom)
        self.lbl_pan_x = QLabel("Deslocamento horizontal")
        self.lbl_pan_x.setObjectName("info_key")
        self.sld_pan_x = self.criar_slider(-100, 100, 0, lambda _: self.renderizar())
        self.lbl_pan_y = QLabel("Deslocamento vertical")
        self.lbl_pan_y.setObjectName("info_key")
        self.sld_pan_y = self.criar_slider(-100, 100, 0, lambda _: self.renderizar())
        for w in (self.lbl_zoom, self.sld_zoom, self.lbl_pan_x, self.sld_pan_x,
                  self.lbl_pan_y, self.sld_pan_y):
            lay.addWidget(w)
        self.sld_pan_x.setEnabled(False)
        self.sld_pan_y.setEnabled(False)
        btn_reset = QPushButton("Restaurar enquadramento")
        btn_reset.setObjectName("btn_ghost")
        btn_reset.clicked.connect(self.resetar_enquadramento)
        lay.addWidget(btn_reset)
        col.addWidget(card)

        card, lay = self.criar_card("Visualização")
        self.btn_fullscreen = QPushButton("Tela cheia  (F11)")
        self.btn_fullscreen.setObjectName("btn_secondary")
        self.btn_fullscreen.clicked.connect(self.alternar_tela_cheia)
        lay.addWidget(self.btn_fullscreen)
        col.addWidget(card)
        col.addStretch()
        tabs.addTab(pagina, "Câmera")
        return tabs

    def criar_area_video(self):
        card = QFrame()
        card.setObjectName("card")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(14, 12, 14, 14)
        lay.setSpacing(10)

        topo = QHBoxLayout()
        t = QLabel("VISUALIZAÇÃO AO VIVO")
        t.setObjectName("card_title")
        self.lbl_fonte = QLabel("Fonte: câmera RTSP")
        self.lbl_fonte.setObjectName("info_key")
        topo.addWidget(t)
        topo.addStretch()
        topo.addWidget(self.lbl_fonte)
        lay.addLayout(topo)

        self.label_video = VideoLabel("Aguardando início da transmissão")
        self.label_video.poligono_finalizado.connect(self.ao_finalizar_poligono)
        self.label_video.retangulo_finalizado.connect(self.ao_finalizar_retangulo)
        self.label_video.setObjectName("video_display")
        self.label_video.setAlignment(Qt.AlignCenter)
        self.label_video.setMinimumSize(480, 320)
        self.label_video.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        lay.addWidget(self.label_video, stretch=1)

        self.alert_label = QLabel("ZONA SEGURA  •  NENHUMA PESSOA NA ÁREA DE PERIGO")
        self.alert_label.setObjectName("alert_safe")
        self.alert_label.setAlignment(Qt.AlignCenter)
        self.alert_label.setFixedHeight(44)
        lay.addWidget(self.alert_label)
        return card

    def criar_painel_status(self):
        scroll = QScrollArea()
        scroll.setFixedWidth(300)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        conteudo = QWidget()
        conteudo.setObjectName("scroll_content")
        col = QVBoxLayout(conteudo)
        col.setContentsMargins(0, 0, 6, 0)
        col.setSpacing(12)
        scroll.setWidget(conteudo)

        card, lay = self.criar_card("Ocupação")
        grade = QGridLayout()
        grade.setSpacing(10)
        self.val_pessoas = self.criar_kpi(grade, 0, "PESSOAS NA IMAGEM", "—")
        self.val_zona = self.criar_kpi(grade, 1, "ÁREA DE PERIGO", "LIVRE")
        lay.addLayout(grade)
        l1, self.val_alertas = self.criar_linha_info("Alertas na sessão", "0")
        lay.addLayout(l1)
        col.addWidget(card)

        card, lay = self.criar_card("Desempenho")
        l1, self.val_fps = self.criar_linha_info("FPS atual", "—")
        lay.addLayout(l1)
        self.grafico_fps = GraficoFPS()
        lay.addWidget(self.grafico_fps)
        l2, self.val_latencia = self.criar_linha_info("Latência de inferência", "—")
        l3, self.val_fps_medio = self.criar_linha_info("FPS médio", "—")
        lay.addLayout(l2)
        lay.addLayout(l3)
        self.fps_hist = []
        col.addWidget(card)

        card, lay = self.criar_card("Sessão")
        l1, self.val_tempo = self.criar_linha_info("Tempo ativo", "00:00:00")
        l2, self.val_capturas = self.criar_linha_info("Capturas salvas", "0")
        lay.addLayout(l1)
        lay.addLayout(l2)
        col.addWidget(card)

        card, lay = self.criar_card("Imagem e calibração")
        l1, self.val_resolucao = self.criar_linha_info("Resolução", "—")
        l2, self.val_megapixels = self.criar_linha_info("Total de pixels", "—")
        lay.addLayout(l1)
        lay.addLayout(l2)

        lbl = QLabel("Fator de escala (mm por pixel)")
        lbl.setObjectName("info_key")
        self.spin_fator = QDoubleSpinBox()
        self.spin_fator.setDecimals(4)
        self.spin_fator.setRange(0.0, 1000.0)
        self.spin_fator.setSingleStep(0.01)
        self.spin_fator.setSpecialValueText("não calibrado")
        self.spin_fator.valueChanged.connect(self.atualizar_calibracao)
        lay.addWidget(lbl)
        lay.addWidget(self.spin_fator)

        btn_cal = QPushButton("Calibrar por referência…")
        btn_cal.setObjectName("btn_secondary")
        btn_cal.clicked.connect(self.abrir_calibracao)
        lay.addWidget(btn_cal)

        l3, self.val_campo = self.criar_linha_info("Campo de visão", "—")
        lay.addLayout(l3)
        col.addWidget(card)

        self.btn_capturar = QPushButton("📷  Capturar imagem  (Ctrl+S)")
        self.btn_capturar.setObjectName("btn_accent")
        self.btn_capturar.setEnabled(False)
        self.btn_capturar.clicked.connect(self.capturar_imagem)
        col.addWidget(self.btn_capturar)

        card, lay = self.criar_card("Eventos recentes")
        self.lista_eventos = QListWidget()
        self.lista_eventos.setMinimumHeight(140)
        lay.addWidget(self.lista_eventos)
        col.addWidget(card)

        col.addStretch()
        return scroll

    def criar_kpi(self, grade, coluna, titulo, valor):
        box = QFrame()
        box.setObjectName("kpi")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(2)
        t = QLabel(titulo)
        t.setObjectName("kpi_title")
        v = QLabel(valor)
        v.setObjectName("kpi_value")
        lay.addWidget(t)
        lay.addWidget(v)
        grade.addWidget(box, 0, coluna)
        return v

    def criar_rodape(self):
        barra = QFrame()
        barra.setObjectName("footer")
        barra.setFixedHeight(30)
        lay = QHBoxLayout(barra)
        lay.setContentsMargins(24, 0, 24, 0)
        self.status_label = QLabel("Pronto para iniciar")
        self.status_label.setObjectName("footer_status")
        lay.addWidget(self.status_label)
        lay.addStretch()
        self.lbl_relogio = QLabel("")
        self.lbl_relogio.setObjectName("footer_status")
        lay.addWidget(self.lbl_relogio)
        return barra

    def definir_badge(self, label, texto, tipo):
        label.setText(texto)
        label.setObjectName("badge")
        label.setProperty("kind", tipo)
        self.repolir(label)

    def repolir(self, w):
        w.style().unpolish(w)
        w.style().polish(w)

    def registrar_evento(self, texto):
        hora = datetime.now().strftime("%H:%M:%S")
        self.lista_eventos.insertItem(0, f"{hora}   {texto}")
        while self.lista_eventos.count() > 100:
            self.lista_eventos.takeItem(self.lista_eventos.count() - 1)

    def iniciar_stream(self):
        if self.video_thread is not None and self.video_thread.isRunning():
            return
        if not self.CAMERA_SOURCE:
            QMessageBox.warning(
                self, "Câmera não configurada",
                "Verifique o endereço RTSP em config.json."
            )
            return

        self.definir_badge(self.camera_badge, "● CONECTANDO CÂMERA", "warning")
        self.definir_badge(self.analysis_badge, "ANÁLISE INICIANDO", "neutral")
        self.btn_iniciar.setEnabled(False)
        self.btn_pausar.setEnabled(True)
        self.btn_parar.setEnabled(True)
        self.total_alertas = 0
        self.val_alertas.setText("0")
        self.fps_hist = []
        self.grafico_fps.limpar()

        self.video_thread = VideoThread(
            camera_source=self.CAMERA_SOURCE,
            model_path=self.MODEL_PATH,
            zona=self.zona,
        )
        self.video_thread.frame_signal.connect(self.atualizar_frame)
        self.video_thread.status_signal.connect(self.atualizar_status)
        self.video_thread.alert_signal.connect(self.alerta_visual)
        self.video_thread.metrics_signal.connect(self.atualizar_metricas)
        self.video_thread.finished.connect(self.thread_finalizada)
        self.video_thread.start()

        self.inicio_sessao = datetime.now()
        self.timer_sessao.start(1000)
        self.registrar_evento("Monitoramento iniciado")

    def pausar_stream(self):
        if self.video_thread and self.video_thread.isRunning():
            self.video_thread.pause()
            self.btn_pausar.setEnabled(False)
            self.btn_reativar.setEnabled(True)
            self.definir_badge(self.analysis_badge, "ANÁLISE PAUSADA", "warning")
            self.registrar_evento("Monitoramento pausado")

    def despausar_stream(self):
        if self.video_thread and self.video_thread.isRunning():
            self.video_thread.resume()
            self.btn_pausar.setEnabled(True)
            self.btn_reativar.setEnabled(False)
            self.definir_badge(self.analysis_badge, "ANÁLISE ATIVA", "ok")
            self.registrar_evento("Monitoramento retomado")

    def parar_stream(self):
        if self.video_thread and self.video_thread.isRunning():
            self.btn_parar.setEnabled(False)
            self.video_thread.stop()
            self.registrar_evento("Monitoramento encerrado pelo operador")

    def thread_finalizada(self):
        self.timer_sessao.stop()
        self.btn_iniciar.setEnabled(True)
        self.btn_pausar.setEnabled(False)
        self.btn_reativar.setEnabled(False)
        self.btn_parar.setEnabled(False)
        self.definir_badge(self.camera_badge, "● CÂMERA OFFLINE", "danger")
        self.definir_badge(self.analysis_badge, "ANÁLISE PARADA", "neutral")
        self.alerta_visual(False)
        self.val_pessoas.setText("—")
        self.val_fps.setText("—")
        self.val_latencia.setText("—")

    def atualizar_frame(self, imagem):
        self.ultima_imagem = imagem
        self.btn_capturar.setEnabled(True)
        self.val_resolucao.setText(f"{imagem.width()} × {imagem.height()} px")
        self.val_megapixels.setText(
            f"{imagem.width() * imagem.height():,}".replace(",", ".")
            + f"  ({imagem.width() * imagem.height() / 1e6:.2f} MP)"
        )
        self.atualizar_calibracao()
        self.renderizar()

    def recorte_rect(self):
        img = self.ultima_imagem
        W, H = img.width(), img.height()
        z = self.sld_zoom.value() / 100.0
        if z <= 1.0:
            return QRect(0, 0, W, H)
        w, h = int(W / z), int(H / z)
        x = int((W - w) / 2 * (1 + self.sld_pan_x.value() / 100.0))
        y = int((H - h) / 2 * (1 + self.sld_pan_y.value() / 100.0))
        return QRect(x, y, w, h)

    def recorte_atual(self):
        img = self.ultima_imagem
        if img is None:
            return None
        r = self.recorte_rect()
        if r.size() == img.size():
            return img
        return img.copy(r)

    def renderizar(self, *_):
        if self.ultima_imagem is None:
            return
        base = QPixmap.fromImage(self.recorte_atual())

        if self.fullscreen_window and self.fullscreen_window.isVisible():
            self.fullscreen_window.atualizar_imagem(base)

        exibido = base.scaled(
            self.label_video.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        if self.chk_grade.isChecked() or self.chk_mira.isChecked():
            p = QPainter(exibido)
            p.setRenderHint(QPainter.Antialiasing)
            p.setPen(QPen(QColor(255, 255, 255, 170), 1))
            w, h = exibido.width(), exibido.height()
            if self.chk_grade.isChecked():
                for i in (1, 2):
                    p.drawLine(w * i // 3, 0, w * i // 3, h)
                    p.drawLine(0, h * i // 3, w, h * i // 3)
            if self.chk_mira.isChecked():
                p.setPen(QPen(QColor(37, 99, 235, 230), 2))
                cx, cy = w // 2, h // 2
                p.drawLine(cx - 24, cy, cx + 24, cy)
                p.drawLine(cx, cy - 24, cx, cy + 24)
                p.drawEllipse(QPointF(cx, cy), 12, 12)
            p.end()
        self.label_video.setPixmap(exibido)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.renderizar()

    def mudou_zoom(self, valor):
        z = valor / 100.0
        self.lbl_zoom.setText(f"Zoom digital: {z:.1f}×")
        ativo = valor > 100
        self.sld_pan_x.setEnabled(ativo)
        self.sld_pan_y.setEnabled(ativo)
        if not ativo:
            self.sld_pan_x.setValue(0)
            self.sld_pan_y.setValue(0)
        self.renderizar()

    def resetar_enquadramento(self):
        self.sld_zoom.setValue(100)
        self.sld_pan_x.setValue(0)
        self.sld_pan_y.setValue(0)
        self.chk_grade.setChecked(False)
        self.chk_mira.setChecked(False)

    def capturar_imagem(self):
        if self.ultima_imagem is None:
            return
        os.makedirs(self.PASTA_CAPTURAS, exist_ok=True)
        nome = datetime.now().strftime("vigia_%Y%m%d_%H%M%S.png")
        caminho = os.path.join(self.PASTA_CAPTURAS, nome)
        if self.ultima_imagem.save(caminho):
            self.total_capturas += 1
            self.val_capturas.setText(str(self.total_capturas))
            self.registrar_evento(f"Imagem capturada: {nome}")
            self.status_label.setText(f"Imagem salva em {os.path.abspath(caminho)}")
        else:
            QMessageBox.warning(self, "Captura", "Não foi possível salvar a imagem.")

    def abrir_calibracao(self):
        dlg = DialogoCalibracao(self)
        if dlg.exec_() == QDialog.Accepted:
            self.spin_fator.setValue(dlg.fator_mm_por_px())
            self.registrar_evento(
                f"Calibração aplicada: {dlg.fator_mm_por_px():.4f} mm/px"
            )

    def atualizar_calibracao(self, *_):
        self.atualizar_info_zona()
        fator = self.spin_fator.value()
        if fator <= 0 or self.ultima_imagem is None:
            self.val_campo.setText("não calibrado" if fator <= 0 else "—")
            return
        larg = self.ultima_imagem.width() * fator / 1000.0
        alt = self.ultima_imagem.height() * fator / 1000.0
        self.val_campo.setText(f"{larg:.2f} × {alt:.2f} m")

    def carregar_zona(self):
        """Carrega polígonos atuais e converte zonas retangulares legadas."""
        try:
            dados = json.loads(self.ZONA_PATH.read_text(encoding="utf-8"))
            faixa_z = dados.get("faixa_z_m", {})
            if isinstance(faixa_z, dict):
                try:
                    z_min = float(faixa_z.get("min", self.z_min_m))
                    z_max = float(faixa_z.get("max", self.z_max_m))
                    if 0 <= z_min < z_max <= 20:
                        self.z_min_m, self.z_max_m = z_min, z_max
                except (TypeError, ValueError):
                    pass

            bruto = dados.get("zona")
            if bruto is None:
                return None

            if isinstance(bruto, dict) and "vertices" in bruto:
                vertices = bruto["vertices"]
            elif isinstance(bruto, dict) and all(
                k in bruto for k in ("centro_x", "centro_y", "largura", "altura")
            ):
                cx = float(bruto["centro_x"])
                cy = float(bruto["centro_y"])
                w = float(bruto["largura"])
                h = float(bruto["altura"])
                ang = math.radians(float(bruto.get("angulo", 0.0)))
                c, sn = math.cos(ang), math.sin(ang)
                vertices = []
                for dx, dy in ((-w/2, -h/2), (w/2, -h/2),
                               (w/2, h/2), (-w/2, h/2)):
                    vertices.append([cx + dx*c - dy*sn, cy + dx*sn + dy*c])
            elif isinstance(bruto, (list, tuple)) and len(bruto) == 5 and all(
                isinstance(v, (int, float)) for v in bruto
            ):
                cx, cy, w, h, angulo = map(float, bruto)
                ang = math.radians(angulo)
                c, sn = math.cos(ang), math.sin(ang)
                vertices = [
                    [cx + dx*c - dy*sn, cy + dx*sn + dy*c]
                    for dx, dy in ((-w/2, -h/2), (w/2, -h/2),
                                   (w/2, h/2), (-w/2, h/2))
                ]
            elif isinstance(bruto, (list, tuple)) and len(bruto) == 4 and all(
                isinstance(v, (int, float)) for v in bruto
            ):
                x1, y1, x2, y2 = map(float, bruto)
                vertices = [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]
            else:
                vertices = bruto

            if not isinstance(vertices, (list, tuple)) or len(vertices) < 3:
                return None
            pontos = [(float(p[0]), float(p[1])) for p in vertices]
            if any(not (0 <= x <= 1 and 0 <= y <= 1) for x, y in pontos):
                return None
            if abs(self.area_poligono(pontos)) < 0.0005:
                return None
            return pontos
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError, IndexError):
            return None

    @staticmethod
    def area_poligono(vertices):
        soma = 0.0
        for i, (x1, y1) in enumerate(vertices):
            x2, y2 = vertices[(i + 1) % len(vertices)]
            soma += x1 * y2 - x2 * y1
        return soma / 2.0

    def salvar_zona(self):
        """Persiste vértices normalizados e limites Z para integração futura."""
        geometria = None if self.zona is None else {
            "vertices": [[float(x), float(y)] for x, y in self.zona]
        }
        dados = {
            "zona": geometria,
            "faixa_z_m": {
                "referencia": "piso",
                "min": self.z_min_m,
                "max": self.z_max_m,
            },
        }
        temporario = self.ZONA_PATH.with_suffix(".tmp")
        try:
            temporario.write_text(
                json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            temporario.replace(self.ZONA_PATH)
            return True
        except OSError as e:
            QMessageBox.warning(self, "Zona de perigo",
                                f"Não foi possível salvar a zona: {e}")
            return False

    def _sincronizar_campos_zona(self):
        if not hasattr(self, "ed_vertices"):
            return
        if self.zona is None:
            self.ed_vertices.clear()
            return
        texto = "\n".join(f"{x*100:.1f}, {y*100:.1f}" for x, y in self.zona)
        self.ed_vertices.setPlainText(texto)

    def alternar_bloqueio_zona(self):
        if self.zona_edicao_liberada:
            self.zona_edicao_liberada = False
            self.btn_zona.setChecked(False)
            self.btn_zona_retangulo.setChecked(False)
            self.label_video.definir_modo_desenho(False)
            self.status_label.setText("Edição da zona bloqueada")
        else:
            senha, ok = QInputDialog.getText(
                self, "Desbloquear edição da zona",
                "Digite a senha do operador:", QLineEdit.Password
            )
            if not ok:
                return
            if senha != self.SENHA_ZONA:
                QMessageBox.warning(self, "Acesso negado", "Senha incorreta.")
                return
            self.zona_edicao_liberada = True
            self.status_label.setText("Edição da zona liberada")
        self._atualizar_estado_edicao_zona()
        self.atualizar_info_zona()

    def aplicar_coordenadas_zona(self):
        if not self.zona_edicao_liberada:
            return
        try:
            vertices = []
            texto = self.ed_vertices.toPlainText().replace(";", "\n")
            for linha in texto.splitlines():
                par = linha.strip().replace("(", "").replace(")", "").replace("%", "")
                if not par:
                    continue
                valores = [v.strip() for v in par.split(",")]
                if len(valores) != 2:
                    raise ValueError("Use um par X,Y por linha, por exemplo: 47.0, 69.0")
                x, y = (float(v) / 100.0 for v in valores)
                if not (0 <= x <= 1 and 0 <= y <= 1):
                    raise ValueError("X e Y devem ficar entre 0 e 100% da imagem.")
                vertices.append((x, y))
        except ValueError as e:
            QMessageBox.warning(self, "Coordenadas inválidas", str(e))
            return
        if len(vertices) < 3:
            QMessageBox.warning(
                self, "Polígono incompleto",
                "Informe pelo menos três linhas no formato X,Y."
            )
            return
        if abs(self.area_poligono(vertices)) < 0.0005:
            QMessageBox.warning(self, "Polígono inválido", "Os vértices formam uma área muito pequena ou degenerada.")
            return
        z_min = self.spin_z_min.value()
        z_max = self.spin_z_max.value()
        if z_min >= z_max:
            QMessageBox.warning(self, "Faixa Z inválida", "O Z mínimo precisa ser menor que o Z máximo.")
            return
        self.z_min_m, self.z_max_m = z_min, z_max
        self.aplicar_zona(vertices)
        self.registrar_evento("Polígono de risco aplicado por coordenadas da imagem")
        self.status_label.setText("Polígono aplicado e salvo (X/Y em % da imagem)")

    def salvar_faixa_z(self):
        if not self.zona_edicao_liberada:
            return
        z_min = self.spin_z_min.value()
        z_max = self.spin_z_max.value()
        if z_min >= z_max:
            QMessageBox.warning(
                self, "Faixa Z inválida",
                "O Z mínimo precisa ser menor que o Z máximo."
            )
            return
        self.z_min_m = z_min
        self.z_max_m = z_max
        if self.salvar_zona():
            texto = (
                f"Faixa Z salva: {z_min:.2f}–{z_max:.2f} m. "
                "Ela ainda não participa dos alertas."
            )
            self.registrar_evento("Limites Z salvos para integração futura")
            self.status_label.setText(texto)

    def _atualizar_estado_edicao_zona(self):
        if not hasattr(self, "btn_zona"):
            return
        liberada = self.zona_edicao_liberada
        for widget in (self.btn_zona, self.btn_zona_retangulo, self.ed_vertices,
                       self.btn_aplicar_coordenadas, self.spin_z_min,
                       self.spin_z_max, self.btn_salvar_faixa_z):
            widget.setEnabled(liberada)
        self.btn_zona_excluir.setEnabled(liberada and self.zona is not None)
        if liberada:
            self.btn_desbloquear_zona.setText("🔓  Bloquear edição")
            self.lbl_estado_edicao.setText(
                "Edição liberada para alterar a zona."
            )
        else:
            self.btn_desbloquear_zona.setText("🔒  Desbloquear edição")
            self.lbl_estado_edicao.setText(
                "Edição bloqueada. A senha é solicitada antes de alterar a zona."
            )

    def aplicar_zona(self, zona):
        self.zona = [(float(x), float(y)) for x, y in zona] if zona is not None else None
        if self.video_thread and self.video_thread.isRunning():
            if self.zona is None:
                self.video_thread.limpar_zona()
            else:
                self.video_thread.definir_zona(self.zona)
        self.salvar_zona()
        self._sincronizar_campos_zona()
        self._atualizar_estado_edicao_zona()
        self.atualizar_info_zona()
        self.renderizar()

    def alternar_modo_desenho(self, ativo):
        if ativo and not self.zona_edicao_liberada:
            self.btn_zona.setChecked(False)
            self.status_label.setText("Desbloqueie a edição antes de desenhar o polígono")
            return
        if ativo:
            self.btn_zona_retangulo.setChecked(False)
            self.label_video.definir_modo_desenho(True, "poligono")
            self.status_label.setText(
                "Clique nos vértices da área de risco; botão direito conclui o polígono."
            )
        elif not self.btn_zona_retangulo.isChecked():
            self.label_video.definir_modo_desenho(False)

    def alternar_modo_retangulo(self, ativo):
        if ativo and not self.zona_edicao_liberada:
            self.btn_zona_retangulo.setChecked(False)
            self.status_label.setText("Desbloqueie a edição antes de desenhar a zona")
            return
        if ativo:
            self.btn_zona.setChecked(False)
            self.label_video.definir_modo_desenho(True, "retangulo")
            self.status_label.setText(
                "Clique e arraste sobre a imagem para desenhar um retângulo de risco."
            )
        elif not self.btn_zona.isChecked():
            self.label_video.definir_modo_desenho(False)

    def ao_finalizar_poligono(self, pontos_tela):
        if not self.zona_edicao_liberada:
            self.btn_zona.setChecked(False)
            return
        rect = self.label_video.retangulo_pixmap()
        if rect is None or self.ultima_imagem is None:
            self.status_label.setText("Inicie a transmissão antes de desenhar a zona")
            self.btn_zona.setChecked(False)
            return
        W, H = self.ultima_imagem.width(), self.ultima_imagem.height()
        recorte = self.recorte_rect()
        vertices = []
        for px, py in pontos_tela:
            ax = min(max((px - rect.x()) / rect.width(), 0.0), 1.0)
            ay = min(max((py - rect.y()) / rect.height(), 0.0), 1.0)
            x = (recorte.x() + ax * recorte.width()) / W
            y = (recorte.y() + ay * recorte.height()) / H
            vertices.append((x, y))

        if len(vertices) < 3 or abs(self.area_poligono(vertices)) < 0.0005:
            self.status_label.setText("Polígono muito pequeno ou degenerado; tente novamente")
            self.btn_zona.setChecked(False)
            return

        self.aplicar_zona(vertices)
        self.registrar_evento(f"Polígono de risco desenhado: {len(vertices)} vértices")
        self.status_label.setText(
            f"Polígono salvo com {len(vertices)} vértices (X/Y em % da imagem)"
        )
        self.btn_zona.setChecked(False)

    def ao_finalizar_retangulo(self, p1, p2):
        if not self.zona_edicao_liberada:
            self.btn_zona_retangulo.setChecked(False)
            return
        rect = self.label_video.retangulo_pixmap()
        if rect is None or self.ultima_imagem is None:
            self.status_label.setText("Inicie a transmissão antes de desenhar a zona")
            self.btn_zona_retangulo.setChecked(False)
            return

        W, H = self.ultima_imagem.width(), self.ultima_imagem.height()
        recorte = self.recorte_rect()

        def converter(ponto):
            ax = min(max((ponto.x() - rect.x()) / rect.width(), 0.0), 1.0)
            ay = min(max((ponto.y() - rect.y()) / rect.height(), 0.0), 1.0)
            x = (recorte.x() + ax * recorte.width()) / W
            y = (recorte.y() + ay * recorte.height()) / H
            return x, y

        a, b = converter(p1), converter(p2)
        x1, x2 = sorted((a[0], b[0]))
        y1, y2 = sorted((a[1], b[1]))
        if x2 - x1 < 0.01 or y2 - y1 < 0.01:
            self.status_label.setText("Retângulo muito pequeno — arraste uma área maior")
            self.btn_zona_retangulo.setChecked(False)
            return

        vertices = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
        self.aplicar_zona(vertices)
        self.registrar_evento("Zona de risco desenhada com arraste do mouse")
        self.status_label.setText("Retângulo de risco aplicado e salvo")
        self.btn_zona_retangulo.setChecked(False)

    def excluir_zona(self):
        if not self.zona_edicao_liberada:
            return
        self.btn_zona.setChecked(False)
        self.btn_zona_retangulo.setChecked(False)
        self.label_video.definir_modo_desenho(False)
        self.aplicar_zona(None)
        self.alerta_visual(False)
        self.registrar_evento("Zona de perigo excluída")
        self.status_label.setText("Zona excluída e remoção salva")

    def atualizar_info_zona(self):
        if not hasattr(self, "lbl_zona_info"):
            return
        if self.zona is None:
            self.lbl_zona_info.setText(
                "Nenhuma zona definida. Desbloqueie a edição para desenhar ou inserir vértices."
            )
            return
        self.lbl_zona_info.setText(
            f"Zona definida com {len(self.zona)} vértices. "
            "Os pares X,Y aparecem acima na ordem do contorno."
        )

    def atualizar_status(self, mensagem):
        self.status_label.setText(mensagem)
        if "Câmera conectada" in mensagem:
            self.definir_badge(self.camera_badge, "● CÂMERA ONLINE", "ok")
            self.definir_badge(self.analysis_badge, "ANÁLISE ATIVA", "ok")
            self.registrar_evento("Câmera conectada")

    def atualizar_metricas(self, fps, pessoas, inferencia_ms):
        self.val_pessoas.setText(str(pessoas))
        self.val_fps.setText(f"{fps:.1f}")
        self.val_latencia.setText(f"{inferencia_ms:.0f} ms")
        self.grafico_fps.adicionar(fps)
        self.fps_hist.append(fps)
        self.val_fps_medio.setText(f"{sum(self.fps_hist) / len(self.fps_hist):.1f}")

    def alerta_visual(self, ativo):
        if ativo and not self.zona_em_alerta:
            self.total_alertas += 1
            self.val_alertas.setText(str(self.total_alertas))
            self.registrar_evento("ALERTA: pessoa na área de perigo")
        elif not ativo and self.zona_em_alerta:
            self.registrar_evento("Área de perigo liberada")
        self.zona_em_alerta = ativo

        if ativo:
            self.alert_label.setText("ALERTA  •  PESSOA DETECTADA NA ÁREA DE PERIGO")
            self.alert_label.setObjectName("alert_active")
            self.val_zona.setText("OCUPADA")
            self.val_zona.setProperty("estado", "perigo")
        else:
            self.alert_label.setText("ZONA SEGURA  •  NENHUMA PESSOA NA ÁREA DE PERIGO")
            self.alert_label.setObjectName("alert_safe")
            self.val_zona.setText("LIVRE")
            self.val_zona.setProperty("estado", "ok")
        self.repolir(self.alert_label)
        self.repolir(self.val_zona)

    def atualizar_tempo_sessao(self):
        if self.inicio_sessao is None:
            return
        s = int((datetime.now() - self.inicio_sessao).total_seconds())
        self.val_tempo.setText(f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}")
        self.lbl_relogio.setText(datetime.now().strftime("%d/%m/%Y  %H:%M:%S"))

    def alternar_tela_cheia(self):
        if self.fullscreen_window and self.fullscreen_window.isVisible():
            self.fullscreen_window.close()
            self.fullscreen_window = None
            return
        self.fullscreen_window = JanelaVideoCheio()
        if self.ultima_imagem is not None:
            self.fullscreen_window.atualizar_imagem(
                QPixmap.fromImage(self.recorte_atual())
            )
        self.fullscreen_window.showFullScreen()

    def aplicar_tema(self):
        self.setStyleSheet("""
            QMainWindow, QWidget#scroll_content { background-color: #f1f5f9; }
            QWidget { color: #0f172a; font-family: 'Segoe UI', Arial, sans-serif; font-size: 12px; }
            QLabel { background: transparent; }
            QScrollArea { background: transparent; border: none; }
            QTabWidget#control_tabs { background: transparent; }
            QTabWidget#control_tabs::pane { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; }
            QTabBar::tab { background: #e2e8f0; color: #475569; min-width: 76px; padding: 8px 4px; margin: 0 3px; border-top-left-radius: 6px; border-top-right-radius: 6px; font-size: 11px; font-weight: 700; }
            QTabBar::tab:selected { background: #1d4ed8; color: #ffffff; }
            QScrollArea#control_scroll { background: transparent; border: none; }
            QWidget#control_page { background: transparent; }
            QLabel#z_warning { color: #92400e; background: #fef3c7; border: 1px solid #fcd34d; border-radius: 6px; padding: 8px; }

            QFrame#header { background-color: #ffffff; border-bottom: 1px solid #e2e8f0; }
            QLabel#app_title { color: #0f2a4a; font-size: 22px; font-weight: 800; letter-spacing: 2px; }
            QLabel#app_subtitle { color: #64748b; font-size: 11px; }

            QLabel#badge { padding: 7px 14px; border-radius: 14px; font-size: 11px; font-weight: 700; }
            QLabel#badge[kind="ok"]      { background: #dcfce7; color: #166534; }
            QLabel#badge[kind="danger"]  { background: #fee2e2; color: #991b1b; }
            QLabel#badge[kind="warning"] { background: #fef3c7; color: #92400e; }
            QLabel#badge[kind="neutral"] { background: #e2e8f0; color: #475569; }

            QFrame#card { background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 10px; }
            QLabel#card_title { color: #475569; font-size: 11px; font-weight: 800; letter-spacing: 1px; }
            QLabel#info_key { color: #64748b; font-size: 12px; }
            QLabel#info_value { color: #0f172a; font-size: 12px; font-weight: 700; }

            QLabel#video_display { background-color: #0b1220; border-radius: 8px; color: #94a3b8; }
            QLabel#alert_safe   { background-color: #dcfce7; color: #166534; border-radius: 8px; font-weight: 800; }
            QLabel#alert_active { background-color: #dc2626; color: #ffffff; border-radius: 8px; font-weight: 800; }

            QFrame#kpi { background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; }
            QLabel#kpi_title { color: #64748b; font-size: 9px; font-weight: 800; }
            QLabel#kpi_value { color: #0f2a4a; font-size: 24px; font-weight: 800; }
            QLabel#kpi_value[estado="ok"] { color: #15803d; }
            QLabel#kpi_value[estado="perigo"] { color: #dc2626; }

            QPushButton { min-height: 34px; border-radius: 6px; font-weight: 700; padding: 0 10px; }
            QPushButton:disabled { background-color: #f1f5f9; color: #94a3b8; border: 1px solid #e2e8f0; }
            QPushButton#btn_primary { background-color: #1d4ed8; color: #ffffff; border: none; min-height: 40px; }
            QPushButton#btn_primary:hover { background-color: #1e40af; }
            QPushButton#btn_secondary { background-color: #ffffff; color: #1e293b; border: 1px solid #cbd5e1; }
            QPushButton#btn_secondary:hover { background-color: #f1f5f9; }
            QPushButton#btn_secondary:checked { background-color: #dbeafe; color: #1d4ed8; border: 1px solid #1d4ed8; }
            QPushButton#btn_danger { background-color: #ffffff; color: #b91c1c; border: 1px solid #fca5a5; }
            QPushButton#btn_danger:hover { background-color: #fef2f2; }
            QPushButton#btn_ghost { background-color: transparent; color: #475569; border: 1px dashed #cbd5e1; }
            QPushButton#btn_accent { background-color: #0f2a4a; color: #ffffff; border: none; min-height: 42px; }
            QPushButton#btn_accent:hover { background-color: #1e3a5f; }

            QCheckBox { spacing: 8px; color: #334155; }
            QSlider::groove:horizontal { height: 4px; background: #e2e8f0; border-radius: 2px; }
            QSlider::sub-page:horizontal { background: #1d4ed8; border-radius: 2px; }
            QSlider::handle:horizontal { background: #ffffff; border: 2px solid #1d4ed8; width: 12px; margin: -6px 0; border-radius: 8px; }
            QSlider::handle:horizontal:disabled { border-color: #cbd5e1; }

            QSpinBox, QDoubleSpinBox, QLineEdit, QPlainTextEdit { background: #ffffff; border: 1px solid #cbd5e1; border-radius: 6px; padding: 6px 8px; min-height: 22px; }
            QListWidget { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; font-size: 11px; }
            QListWidget::item { padding: 4px 6px; }

            QFrame#footer { background-color: #ffffff; border-top: 1px solid #e2e8f0; }
            QLabel#footer_status { color: #64748b; font-size: 11px; }
            QDialog { background: #ffffff; }
        """)

    def closeEvent(self, event):
        self.zona_edicao_liberada = False
        if self.video_thread and self.video_thread.isRunning():
            self.video_thread.stop()
        if self.fullscreen_window:
            self.fullscreen_window.close()
        event.accept()


if __name__ == "__main__":
    import sys
    from PyQt5.QtWidgets import QApplication

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

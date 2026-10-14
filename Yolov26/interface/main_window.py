import json
import math
import os
from pathlib import Path
from collections import deque
from datetime import datetime

from PyQt5.QtCore import Qt, QTimer, QRectF, QPointF, QSize, QUrl, pyqtSignal
from PyQt5.QtGui import (
    QKeySequence, QPainter, QPen, QColor, QPolygonF, QBrush, QIcon, QPixmap,
    QDesktopServices,
)
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QSizePolicy, QFrame, QShortcut, QSlider, QCheckBox, QDoubleSpinBox, QSpinBox,
    QListWidget, QScrollArea, QComboBox, QStackedWidget, QGridLayout, QDialog,
    QDialogButtonBox, QFormLayout, QToolButton, QMenu, QAction, QAbstractSpinBox,
    QApplication, QMessageBox, QInputDialog, QLineEdit, QListWidgetItem,
)

from interface.video_thread import VideoThread

# ============================================================================
# Paleta
# ============================================================================
PALETA = {
    "@FUNDO@": "#f0f0f0",
    "@PAINEL@": "#ffffff",
    "@BORDA@": "#dedede",
    "@TEXTO@": "#1f1f1f",
    "@MUTED@": "#6b6b6b",
    "@VERDE@": "#16a34a",
    "@VERDE_ESC@": "#166534",
    "@VERDE_HOVER@": "#15803d",
    "@VERDE_LINHA@": "#22c55e",
    "@VERDE_SUAVE@": "#bbf7d0",
    "@VERDE_FUNDO@": "#ecfdf3",
}

CORES_ZONA = [
    ("Vermelho", "#dc2626"), ("Laranja", "#f97316"), ("Amarelo", "#eab308"),
    ("Verde", "#16a34a"), ("Azul", "#2563eb"), ("Roxo", "#9333ea"),
]

# ============================================================================
# Ícones vetoriais
# ============================================================================
def _desenhar_icone(p, nome):
    if nome == "play":
        p.drawPolygon(QPolygonF([QPointF(9.5, 5.5), QPointF(9.5, 22.5), QPointF(22.5, 14)]))
    elif nome == "pause":
        p.drawRoundedRect(QRectF(8, 6, 4, 16), 1.2, 1.2)
        p.drawRoundedRect(QRectF(16, 6, 4, 16), 1.2, 1.2)
    elif nome == "stop":
        p.drawRoundedRect(QRectF(7, 7, 14, 14), 2, 2)
    elif nome == "camera":
        p.drawRoundedRect(QRectF(3.5, 9, 21, 14), 3, 3)
        p.drawEllipse(QPointF(14, 16), 4.2, 4.2)
        p.drawPolyline(QPolygonF([QPointF(10, 9), QPointF(11.5, 5.5),
                                  QPointF(16.5, 5.5), QPointF(18, 9)]))
    elif nome == "zona":
        pts = [QPointF(14, 4.5), QPointF(23.5, 11), QPointF(20.5, 22.5),
               QPointF(7.5, 22.5), QPointF(4.5, 11)]
        p.drawPolygon(QPolygonF(pts))
        p.setBrush(QBrush(p.pen().color()))
        for pt in pts:
            p.drawEllipse(pt, 1.7, 1.7)
    elif nome == "regua":
        p.save()
        p.translate(14, 14)
        p.rotate(-45)
        p.drawRoundedRect(QRectF(-11, -4.5, 22, 9), 1.5, 1.5)
        for x in (-6.5, -2.5, 1.5, 5.5):
            p.drawLine(QPointF(x, -4.5), QPointF(x, -0.5))
        p.restore()
    elif nome == "menu":
        for y in (8, 14, 20):
            p.drawLine(QPointF(5, y), QPointF(23, y))


def icone(nome, normal="#525252", ativo="#15803d", desab="#c8c8c8", tam=28):
    ic = QIcon()

    def pm(cor):
        pix = QPixmap(tam * 2, tam * 2)
        pix.setDevicePixelRatio(2)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor(cor), 1.8)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        _desenhar_icone(p, nome)
        p.end()
        return pix

    n, a, d = pm(normal), pm(ativo), pm(desab)
    ic.addPixmap(n, QIcon.Normal, QIcon.Off)
    ic.addPixmap(n, QIcon.Active, QIcon.Off)
    ic.addPixmap(a, QIcon.Normal, QIcon.On)
    ic.addPixmap(a, QIcon.Active, QIcon.On)
    ic.addPixmap(d, QIcon.Disabled, QIcon.Off)
    ic.addPixmap(d, QIcon.Disabled, QIcon.On)
    return ic


# ============================================================================
# Controle slider genérico (sem spinbox decimal complexa)
# ============================================================================
class ParamSlider(QWidget):
    alterado = pyqtSignal(float)

    def __init__(self, rotulo, minimo, maximo, valor, sufixo="", decimais=0, parent=None):
        super().__init__(parent)
        self.f = 10 ** decimais
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)

        topo = QHBoxLayout()
        lbl = QLabel(rotulo)
        lbl.setObjectName("param_rotulo")
        self.spin = QDoubleSpinBox()
        self.spin.setDecimals(decimais)
        self.spin.setRange(minimo, maximo)
        self.spin.setSuffix(sufixo)
        self.spin.setValue(valor)
        self.spin.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spin.setAlignment(Qt.AlignRight)
        self.spin.setFixedWidth(84)
        topo.addWidget(lbl)
        topo.addStretch()
        topo.addWidget(self.spin)
        lay.addLayout(topo)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(int(round(minimo * self.f)), int(round(maximo * self.f)))
        self.slider.setValue(int(round(valor * self.f)))
        lay.addWidget(self.slider)

        self.slider.valueChanged.connect(self._slider_mudou)
        self.spin.valueChanged.connect(self._spin_mudou)

    def _slider_mudou(self, i):
        self.spin.blockSignals(True)
        self.spin.setValue(i / self.f)
        self.spin.blockSignals(False)
        self.alterado.emit(i / self.f)

    def _spin_mudou(self, v):
        self.slider.blockSignals(True)
        self.slider.setValue(int(round(v * self.f)))
        self.slider.blockSignals(False)
        self.alterado.emit(float(v))

    def valor(self):
        return self.spin.value()

    def definir(self, v):
        self.spin.blockSignals(True)
        self.slider.blockSignals(True)
        self.spin.setValue(v)
        self.slider.setValue(int(round(v * self.f)))
        self.spin.blockSignals(False)
        self.slider.blockSignals(False)


# ============================================================================
# Gráfico de linha
# ============================================================================
class GraficoLinha(QWidget):
    def __init__(self, cor="#16a34a", topo_min=30.0, pontos=60, altura=80):
        super().__init__()
        self.cor = QColor(cor)
        self.topo_min = topo_min
        self.valores = deque(maxlen=pontos)
        self.setFixedHeight(altura)
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
        p.fillRect(self.rect(), QColor("#fafafa"))
        r = self.rect().adjusted(6, 8, -6, -6)
        p.setPen(QPen(QColor("#e6e6e6"), 1))
        for i in range(3):
            y = r.top() + i * r.height() / 2
            p.drawLine(r.left(), int(y), r.right(), int(y))
        p.setPen(QPen(QColor("#e3e3e3"), 1))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))

        if len(self.valores) < 2:
            p.setPen(QColor("#a3a3a3"))
            p.drawText(self.rect(), Qt.AlignCenter, "sem dados")
            return

        topo = max(self.topo_min, max(self.valores) * 1.15)
        passo = r.width() / (self.valores.maxlen - 1)
        x0 = r.right() - (len(self.valores) - 1) * passo
        pts = [QPointF(x0 + i * passo, r.bottom() - (v / topo) * r.height())
               for i, v in enumerate(self.valores)]

        area = QPolygonF(pts + [QPointF(pts[-1].x(), r.bottom()), QPointF(pts[0].x(), r.bottom())])
        fill = QColor(self.cor)
        fill.setAlpha(34)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(fill))
        p.drawPolygon(area)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(self.cor, 1.8))
        p.drawPolyline(QPolygonF(pts))
        p.setPen(QColor("#9a9a9a"))
        p.drawText(r.left() + 2, r.top() + 2, f"{topo:.0f}")


# ============================================================================
# Visualização de Vídeo e Desenho Livre de Polígonos
# ============================================================================
class VideoView(QWidget):
    zona_alterada = pyqtSignal(object)            # lista de zonas durante arraste
    zona_edicao_concluida = pyqtSignal(object)    # salvar após soltar o mouse
    zona_criada = pyqtSignal(object)
    zona_selecionada = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self.setMouseTracking(True)
        self.setMinimumSize(480, 320)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.imagem = None
        self.zoom = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.grade = False
        self.mira = False
        self.zonas = []                    # [(vertices_normalizados, cor_hex), ...]
        self.zona_selecionada_idx = -1
        self.alerta = False
        self.bloqueada = True
        self.cor = "#dc2626"
        self.modo_desenho = False
        self.pontos_desenho = []
        self.pos_mouse_w = None
        self._drag = None

    def set_frame(self, img):
        self.imagem = img
        self.update()

    def set_zonas(self, zonas, selecionada=None):
        self.zonas = list(zonas or [])
        if selecionada is not None:
            self.zona_selecionada_idx = selecionada
        if not (0 <= self.zona_selecionada_idx < len(self.zonas)):
            self.zona_selecionada_idx = len(self.zonas) - 1
        self.update()

    def set_zona(self, zona):
        """Compatibilidade com chamadas antigas de zona única."""
        self.set_zonas([] if zona is None else [zona], 0 if zona is not None else -1)

    def set_enquadramento(self, zoom=None, pan_x=None, pan_y=None):
        if zoom is not None:
            self.zoom = max(1.0, zoom)
        if pan_x is not None:
            self.pan_x = pan_x
        if pan_y is not None:
            self.pan_y = pan_y
        self.update()

    def definir_modo_desenho(self, ativo):
        self.modo_desenho = bool(ativo and not self.bloqueada)
        self.pontos_desenho = []
        self._drag = None
        self.setCursor(Qt.CrossCursor if self.modo_desenho else Qt.ArrowCursor)
        self.update()

    def _wh(self):
        if self.imagem is None:
            return 1, 1
        return self.imagem.width(), self.imagem.height()

    def crop_rect(self):
        W, H = self._wh()
        z = max(1.0, self.zoom)
        w, h = W / z, H / z
        x = (W - w) / 2 * (1 + self.pan_x / 100.0)
        y = (H - h) / 2 * (1 + self.pan_y / 100.0)
        return QRectF(x, y, w, h)

    def _geo(self):
        crop = self.crop_rect()
        s = min(self.width() / crop.width(), self.height() / crop.height())
        ox = (self.width() - crop.width() * s) / 2
        oy = (self.height() - crop.height() * s) / 2
        return crop, s, ox, oy

    def f2w(self, x, y):
        crop, s, ox, oy = self._geo()
        return QPointF(ox + (x - crop.x()) * s, oy + (y - crop.y()) * s)

    def w2f(self, p):
        crop, s, ox, oy = self._geo()
        return QPointF(crop.x() + (p.x() - ox) / s, crop.y() + (p.y() - oy) / s)

    def _poligono_w(self, zona):
        W, H = self._wh()
        return QPolygonF([self.f2w(p[0] * W, p[1] * H) for p in zona[0]])

    def _alcas(self, zona):
        W, H = self._wh()
        return {i: self.f2w(p[0] * W, p[1] * H) for i, p in enumerate(zona[0])}

    def _hit(self, pos, zona):
        for i, pt in self._alcas(zona).items():
            if math.hypot(pos.x() - pt.x(), pos.y() - pt.y()) <= 9:
                return ("vertice", i)
        if self._poligono_w(zona).containsPoint(pos, Qt.OddEvenFill):
            return ("move",)
        return None

    def _emitir(self, indice, zona):
        self.zonas[indice] = zona
        self.update()
        self.zona_alterada.emit(list(self.zonas))

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.fillRect(self.rect(), QColor("#0c110e"))
        if self.imagem is None:
            p.setPen(QColor("#8b9490"))
            p.drawText(self.rect(), Qt.AlignCenter, "Inicie o monitoramento para ver a imagem")
            return

        crop, escala, ox, oy = self._geo()
        alvo = QRectF(ox, oy, crop.width() * escala, crop.height() * escala)
        p.drawImage(alvo, self.imagem, crop)
        p.save()
        p.setClipRect(alvo)

        if self.grade:
            p.setPen(QPen(QColor(255, 255, 255, 120), 1))
            for i in (1, 2):
                x = alvo.left() + alvo.width() * i / 3
                y = alvo.top() + alvo.height() * i / 3
                p.drawLine(QPointF(x, alvo.top()), QPointF(x, alvo.bottom()))
                p.drawLine(QPointF(alvo.left(), y), QPointF(alvo.right(), y))
        if self.mira:
            p.setPen(QPen(QColor(34, 197, 94, 230), 1.6))
            c = alvo.center()
            p.drawLine(QPointF(c.x() - 26, c.y()), QPointF(c.x() + 26, c.y()))
            p.drawLine(QPointF(c.x(), c.y() - 26), QPointF(c.x(), c.y() + 26))
            p.drawEllipse(c, 13, 13)

        if self.modo_desenho and self.pontos_desenho:
            W, H = self._wh()
            pontos_w = [self.f2w(x * W, y * H) for x, y in self.pontos_desenho]
            cor = QColor(self.cor)
            p.setPen(QPen(cor, 2, Qt.DashLine))
            if len(pontos_w) > 1:
                p.drawPolyline(QPolygonF(pontos_w))
            if self.pos_mouse_w is not None:
                p.drawLine(pontos_w[-1], self.pos_mouse_w)
            p.setBrush(QBrush(cor))
            for pt in pontos_w:
                p.drawEllipse(pt, 4, 4)

        for i, zona in enumerate(self.zonas):
            cor = QColor(zona[1])
            preenchimento = QColor(cor)
            preenchimento.setAlpha(95 if self.alerta else (52 if i == self.zona_selecionada_idx else 32))
            borda = QColor(cor)
            borda.setAlpha(220 if i == self.zona_selecionada_idx else 175)
            caneta = QPen(borda, 2.0 if i == self.zona_selecionada_idx else 1.3)
            caneta.setJoinStyle(Qt.RoundJoin)
            p.setPen(caneta)
            p.setBrush(QBrush(preenchimento))
            p.drawPolygon(self._poligono_w(zona))
        p.restore()

        if not self.bloqueada and not self.modo_desenho and 0 <= self.zona_selecionada_idx < len(self.zonas):
            zona = self.zonas[self.zona_selecionada_idx]
            cor = QColor(zona[1])
            p.setPen(QPen(cor, 1.4))
            p.setBrush(QBrush(QColor("#ffffff")))
            for pt in self._alcas(zona).values():
                p.drawRect(QRectF(pt.x() - 4.5, pt.y() - 4.5, 9, 9))

    def _atualizar_cursor(self, pos):
        if self.modo_desenho:
            self.setCursor(Qt.CrossCursor)
            return
        if self.imagem is not None and not self.bloqueada:
            for zona in reversed(self.zonas):
                hit = self._hit(pos, zona)
                if hit:
                    self.setCursor(Qt.SizeAllCursor if hit[0] == "move" else Qt.PointingHandCursor)
                    return
        self.setCursor(Qt.ArrowCursor)

    def mousePressEvent(self, e):
        if self.imagem is None:
            return
        pos = QPointF(e.pos())
        if self.modo_desenho and not self.bloqueada:
            if e.button() == Qt.LeftButton:
                f = self.w2f(pos)
                W, H = self._wh()
                self.pontos_desenho.append((min(max(f.x() / W, 0.0), 1.0),
                                            min(max(f.y() / H, 0.0), 1.0)))
                self.update()
            elif e.button() == Qt.RightButton:
                if len(self.pontos_desenho) >= 3:
                    self.zona_criada.emit((self.pontos_desenho, self.cor))
                self.pontos_desenho = []
                self.definir_modo_desenho(False)
            return

        if e.button() != Qt.LeftButton or self.bloqueada:
            return
        for indice in reversed(range(len(self.zonas))):
            zona = self.zonas[indice]
            hit = self._hit(pos, zona)
            if hit is None:
                continue
            self.zona_selecionada_idx = indice
            self.zona_selecionada.emit(indice)
            if hit[0] == "move":
                f = self.w2f(pos)
                self._drag = ("move", indice, f, list(zona[0]))
            else:
                self._drag = ("vertice", indice, hit[1])
            self.update()
            return

    def mouseMoveEvent(self, e):
        pos = QPointF(e.pos())
        self.pos_mouse_w = pos
        if self.modo_desenho:
            self.update()
        if self._drag is None or self.imagem is None:
            if self.imagem is not None:
                self._atualizar_cursor(pos)
            return

        W, H = self._wh()
        f = self.w2f(pos)
        tipo, indice = self._drag[0], self._drag[1]
        zona = self.zonas[indice]
        pontos = list(zona[0])
        if tipo == "move":
            clique_inicial, pontos_iniciais = self._drag[2], self._drag[3]
            dx = (f.x() - clique_inicial.x()) / W
            dy = (f.y() - clique_inicial.y()) / H
            pontos = [(min(max(x + dx, 0.0), 1.0), min(max(y + dy, 0.0), 1.0))
                      for x, y in pontos_iniciais]
        else:
            indice_vertice = self._drag[2]
            pontos[indice_vertice] = (min(max(f.x() / W, 0.0), 1.0),
                                      min(max(f.y() / H, 0.0), 1.0))
        self._emitir(indice, (pontos, zona[1]))

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton or self._drag is None:
            return
        self._drag = None
        self._atualizar_cursor(QPointF(e.pos()))
        self.zona_edicao_concluida.emit(list(self.zonas))

    def wheelEvent(self, e):
        e.ignore()


# ============================================================================
# Diálogo de calibração por referência
# ============================================================================
class DialogoCalibracao(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Calibrar por referência")
        form = QFormLayout(self)
        self.real_mm = QDoubleSpinBox()
        self.real_mm.setRange(0.1, 1000000)
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


# ============================================================================
# Janela principal
# ============================================================================
class MainWindow(QMainWindow):
    PASTA_CAPTURAS = "capturas"
    SENHA_ZONA = "MURUIA"
    LARG_TRILHO = 70
    LARG_FLYOUT = 316
    LARG_STATUS = 340

    def __init__(self):
        super().__init__()
        self.setWindowTitle("VIGIA | Monitoramento Inteligente")
        self.resize(1520, 880)
        self.setMinimumSize(1180, 700)

        self.ROOT_DIR = Path(__file__).resolve().parent.parent
        self.MODEL_PATH = str(self.ROOT_DIR / "yolo26n.pt")
        self.ZONA_PATH = self.ROOT_DIR / "zona_perigo.json"

        self.video_thread = None
        self.ultima_imagem = None
        self.zonas = self.carregar_zonas()
        self.zona_selecionada_idx = 0 if self.zonas else -1
        self.cor_nova_zona = PALETA.get("@VERMELHO@", "#dc2626")
        self.edicao_zona_liberada = False
        self.zona_em_alerta = False
        self.pausado = False
        self.total_alertas = 0
        self.total_capturas = 0
        self.inicio_sessao = None
        self.fps_hist = []
        self._res = None
        self._topico = None

        self.init_ui()
        self.aplicar_tema()
        self.selecionar_topico(0)
        self.view.set_zonas(self.zonas, self.zona_selecionada_idx)
        self.atualizar_lista_zonas()
        self.atualizar_estado_edicao_zonas()
        self.atualizar_botoes()
        self.atualizar_info_zona()
        self.atualizar_barra_alerta()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(1000)
        self.tick()

        QShortcut(QKeySequence("F11"), self).activated.connect(self.alternar_tela_cheia)
        QShortcut(QKeySequence("Esc"), self).activated.connect(self.tecla_esc)

    def linha_h(self, suave=False):
        l = QFrame()
        l.setFrameShape(QFrame.NoFrame)
        l.setObjectName("linha_verde_suave" if suave else "linha_verde")
        l.setFixedHeight(1 if suave else 2)
        return l

    def linha_v(self):
        l = QFrame()
        l.setFrameShape(QFrame.NoFrame)
        l.setObjectName("linha_verde")
        l.setFixedWidth(2)
        return l

    def rotulo(self, texto, obj="dica"):
        l = QLabel(texto)
        l.setObjectName(obj)
        l.setWordWrap(True)
        return l

    def secao(self, titulo):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 14, 16, 16)
        lay.setSpacing(10)
        t = QLabel(titulo.upper())
        t.setObjectName("secao_titulo")
        lay.addWidget(t)
        return w, lay

    def cartao(self, titulo):
        c = QFrame()
        c.setObjectName("cartao")
        lay = QVBoxLayout(c)
        lay.setContentsMargins(14, 12, 14, 14)
        lay.setSpacing(8)
        t = QLabel(titulo.upper())
        t.setObjectName("secao_titulo")
        lay.addWidget(t)
        return c, lay

    def linha_info(self, rotulo, valor="—"):
        linha = QHBoxLayout()
        a = QLabel(rotulo)
        a.setObjectName("info_chave")
        b = QLabel(valor)
        b.setObjectName("info_valor")
        b.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        linha.addWidget(a)
        linha.addStretch()
        linha.addWidget(b)
        return linha, b

    def kpi(self, titulo, valor):
        box = QFrame()
        box.setObjectName("kpi")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(12, 9, 12, 10)
        lay.setSpacing(0)
        t = QLabel(titulo)
        t.setObjectName("kpi_titulo")
        v = QLabel(valor)
        v.setObjectName("kpi_valor")
        lay.addWidget(t)
        lay.addWidget(v)
        return box, v

    def repolir(self, w):
        w.style().unpolish(w)
        w.style().polish(w)

    def definir_badge(self, label, texto, tipo):
        label.setText(texto)
        label.setObjectName("badge")
        label.setProperty("kind", tipo)
        self.repolir(label)

    def status(self, msg):
        self.status_label.setText(msg)

    def registrar_evento(self, texto):
        hora = datetime.now().strftime("%H:%M:%S")
        self.lista_eventos.insertItem(0, f"{hora}   {texto}")
        while self.lista_eventos.count() > 100:
            self.lista_eventos.takeItem(self.lista_eventos.count() - 1)

    def init_ui(self):
        self.view = VideoView()
        self.view.zona_alterada.connect(lambda zs: self.aplicar_zonas(zs, persistir=False))
        self.view.zona_edicao_concluida.connect(lambda zs: self.aplicar_zonas(zs, persistir=True))
        self.view.zona_criada.connect(self.ao_zona_criada)
        self.view.zona_selecionada.connect(self.selecionar_zona)

        self.criar_acoes()

        central = QWidget()
        central.setObjectName("raiz")
        self.setCentralWidget(central)
        raiz = QVBoxLayout(central)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)

        raiz.addWidget(self.criar_barra_superior())
        raiz.addWidget(self.linha_h())

        corpo = QHBoxLayout()
        corpo.setSpacing(0)
        corpo.addWidget(self.criar_trilho())
        corpo.addWidget(self.linha_v())
        self.flyout = self.criar_flyout()
        self.sep_flyout = self.linha_v()
        corpo.addWidget(self.flyout)
        corpo.addWidget(self.sep_flyout)
        corpo.addWidget(self.criar_area_video(), 1)
        corpo.addWidget(self.linha_v())
        corpo.addWidget(self.criar_painel_status())
        raiz.addLayout(corpo, 1)

        raiz.addWidget(self.linha_h(suave=True))
        raiz.addWidget(self.criar_rodape())

    def criar_acoes(self):
        self.act_iniciar = QAction(icone("play"), "Iniciar", self)
        self.act_pausar = QAction(icone("pause"), "Pausar", self)
        self.act_parar = QAction(icone("stop"), "Parar", self)
        self.act_capturar = QAction(icone("camera"), "Capturar", self)
        self.act_capturar.setShortcut(QKeySequence("Ctrl+S"))
        self.act_iniciar.triggered.connect(self.iniciar_stream)
        self.act_pausar.triggered.connect(self.pausar_stream)
        self.act_parar.triggered.connect(self.parar_stream)
        self.act_capturar.triggered.connect(self.capturar_imagem)
        for a in (self.act_iniciar, self.act_pausar, self.act_parar, self.act_capturar):
            self.addAction(a)

    def criar_barra_superior(self):
        barra = QFrame()
        barra.setObjectName("barra_superior")
        barra.setFixedHeight(64)
        lay = QHBoxLayout(barra)
        lay.setContentsMargins(8, 6, 16, 6)
        lay.setSpacing(4)

        self.btn_menu = QToolButton()
        self.btn_menu.setObjectName("btn_menu")
        self.btn_menu.setText("Menu")
        self.btn_menu.setIcon(icone("menu", normal="#ffffff"))
        self.btn_menu.setIconSize(QSize(24, 24))
        self.btn_menu.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.btn_menu.setPopupMode(QToolButton.InstantPopup)
        self.btn_menu.setFixedSize(self.LARG_TRILHO - 8, 52)
        menu = QMenu(self.btn_menu)
        menu.addAction("Capturar imagem", self.capturar_imagem)
        menu.addAction("Abrir pasta de capturas", self.abrir_pasta_capturas)
        menu.addSeparator()
        menu.addAction("Tela cheia (F11)", self.alternar_tela_cheia)
        menu.addSeparator()
        menu.addAction("Sair", self.close)
        self.btn_menu.setMenu(menu)
        lay.addWidget(self.btn_menu)
        lay.addSpacing(14)

        marca = QVBoxLayout()
        marca.setSpacing(0)
        t = QLabel("VIGIA")
        t.setObjectName("app_titulo")
        s = QLabel("Monitoramento inteligente de área")
        s.setObjectName("app_subtitulo")
        marca.addStretch()
        marca.addWidget(t)
        marca.addWidget(s)
        marca.addStretch()
        lay.addLayout(marca)
        lay.addSpacing(22)

        for act in (self.act_iniciar, self.act_pausar, self.act_parar, self.act_capturar):
            b = QToolButton()
            b.setObjectName("btn_barra")
            b.setDefaultAction(act)
            b.setIconSize(QSize(24, 24))
            b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            b.setFixedSize(66, 52)
            lay.addWidget(b)

        lay.addStretch()
        self.camera_badge = QLabel()
        self.analysis_badge = QLabel()
        self.definir_badge(self.camera_badge, "● CÂMERA OFFLINE", "danger")
        self.definir_badge(self.analysis_badge, "ANÁLISE PARADA", "neutral")
        lay.addWidget(self.camera_badge)
        lay.addSpacing(6)
        lay.addWidget(self.analysis_badge)
        return barra

    def criar_trilho(self):
        trilho = QFrame()
        trilho.setObjectName("trilho")
        trilho.setFixedWidth(self.LARG_TRILHO)
        lay = QVBoxLayout(trilho)
        lay.setContentsMargins(0, 8, 0, 8)
        lay.setSpacing(2)
        self.btns_trilho = []
        topicos = [("Operação", "play"), ("Câmera", "camera"),
                   ("Zona", "zona"), ("Calibração", "regua")]
        for i, (txt, ic) in enumerate(topicos):
            b = QToolButton()
            b.setObjectName("btn_trilho")
            b.setText(txt)
            b.setIcon(icone(ic))
            b.setIconSize(QSize(26, 26))
            b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            b.setCheckable(True)
            b.setFixedHeight(64)
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            b.clicked.connect(lambda _, idx=i: self.selecionar_topico(idx))
            lay.addWidget(b)
            self.btns_trilho.append(b)
        lay.addStretch()
        return trilho

    def selecionar_topico(self, i):
        if self._topico == i:
            self._topico = None
            self.flyout.hide()
            self.sep_flyout.hide()
        else:
            self._topico = i
            self.stack.setCurrentIndex(i)
            self.flyout.show()
            self.sep_flyout.show()
        for k, b in enumerate(self.btns_trilho):
            b.setChecked(self._topico == k)

    def criar_flyout(self):
        f = QWidget()
        f.setObjectName("flyout")
        f.setFixedWidth(self.LARG_FLYOUT)
        lay = QVBoxLayout(f)
        lay.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        self.stack.addWidget(self.pagina_operacao())
        self.stack.addWidget(self.pagina_camera())
        self.stack.addWidget(self.pagina_zona())
        self.stack.addWidget(self.pagina_calibracao())
        lay.addWidget(self.stack)
        return f

    def criar_pagina(self, titulo, descricao, secoes):
        raiz = QWidget()
        raiz.setObjectName("pagina")
        lay = QVBoxLayout(raiz)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        cab = QWidget()
        cl = QVBoxLayout(cab)
        cl.setContentsMargins(16, 14, 16, 12)
        cl.setSpacing(2)
        t = QLabel(titulo)
        t.setObjectName("pagina_titulo")
        cl.addWidget(t)
        cl.addWidget(self.rotulo(descricao, "pagina_desc"))
        lay.addWidget(cab)
        lay.addWidget(self.linha_h())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        conteudo = QWidget()
        conteudo.setObjectName("conteudo_pagina")
        cl2 = QVBoxLayout(conteudo)
        cl2.setContentsMargins(0, 0, 0, 0)
        cl2.setSpacing(0)
        for i, sec in enumerate(secoes):
            cl2.addWidget(sec)
            if i < len(secoes) - 1:
                cl2.addWidget(self.linha_h(suave=True))
        cl2.addStretch()
        scroll.setWidget(conteudo)
        lay.addWidget(scroll, 1)
        return raiz

    def pagina_operacao(self):
        s1, l1 = self.secao("Controle da análise")
        self.btn_iniciar = QPushButton("Iniciar monitoramento")
        self.btn_iniciar.setObjectName("btn_primary")
        self.btn_pausar = QPushButton("Pausar")
        self.btn_pausar.setObjectName("btn_secondary")
        self.btn_parar = QPushButton("Parar")
        self.btn_parar.setObjectName("btn_danger")
        self.btn_iniciar.clicked.connect(self.iniciar_stream)
        self.btn_pausar.clicked.connect(self.pausar_stream)
        self.btn_parar.clicked.connect(self.parar_stream)
        l1.addWidget(self.btn_iniciar)
        linha = QHBoxLayout()
        linha.addWidget(self.btn_pausar)
        linha.addWidget(self.btn_parar)
        l1.addLayout(linha)

        s2, l2 = self.secao("Detecção")
        self.p_conf = ParamSlider("Confiança mínima", 10, 95, 50, " %")
        self.p_conf.alterado.connect(self.mudou_confianca)
        l2.addWidget(self.p_conf)

        s3, l3 = self.secao("Fonte de vídeo")
        linha = QHBoxLayout()
        linha.addWidget(QLabel("Índice da câmera"))
        linha.addStretch()
        self.spin_camera = QSpinBox()
        self.spin_camera.setRange(0, 10)
        self.spin_camera.setFixedWidth(84)
        self.spin_camera.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spin_camera.setAlignment(Qt.AlignRight)
        linha.addWidget(self.spin_camera)
        l3.addLayout(linha)

        return self.criar_pagina("Operação", "Controle da análise em tempo real.", [s1, s2, s3])

    def pagina_camera(self):
        s1, l1 = self.secao("Captura de imagem")
        self.btn_capturar_painel = QPushButton("Capturar imagem  (Ctrl+S)")
        self.btn_capturar_painel.setObjectName("btn_dark")
        self.btn_capturar_painel.clicked.connect(self.capturar_imagem)
        l1.addWidget(self.btn_capturar_painel)
        linha = QHBoxLayout()
        linha.addWidget(QLabel("Formato do arquivo"))
        linha.addStretch()
        self.combo_formato = QComboBox()
        self.combo_formato.addItems(["PNG", "JPG"])
        self.combo_formato.setFixedWidth(84)
        linha.addWidget(self.combo_formato)
        l1.addLayout(linha)
        self.chk_cap_zona = QCheckBox("Incluir zona de perigo na imagem")
        self.chk_cap_zona.setChecked(True)
        l1.addWidget(self.chk_cap_zona)
        btn_pasta = QPushButton("Abrir pasta de capturas")
        btn_pasta.setObjectName("btn_secondary")
        btn_pasta.clicked.connect(self.abrir_pasta_capturas)
        l1.addWidget(btn_pasta)

        s2, l2 = self.secao("Enquadramento")
        self.p_zoom = ParamSlider("Zoom digital", 100, 400, 100, " %")
        self.p_pan_x = ParamSlider("Deslocamento horizontal", -100, 100, 0, " %")
        self.p_pan_y = ParamSlider("Deslocamento vertical", -100, 100, 0, " %")
        for p in (self.p_zoom, self.p_pan_x, self.p_pan_y):
            p.alterado.connect(self.mudou_enquadramento)
            l2.addWidget(p)
        btn_reset = QPushButton("Restaurar enquadramento")
        btn_reset.setObjectName("btn_ghost")
        btn_reset.clicked.connect(self.resetar_enquadramento)
        l2.addWidget(btn_reset)

        s3, l3 = self.secao("Guias de alinhamento")
        self.chk_grade = QCheckBox("Grade 3 × 3")
        self.chk_mira = QCheckBox("Mira central")
        self.chk_grade.toggled.connect(lambda v: (setattr(self.view, "grade", v), self.view.update()))
        self.chk_mira.toggled.connect(lambda v: (setattr(self.view, "mira", v), self.view.update()))
        l3.addWidget(self.chk_grade)
        l3.addWidget(self.chk_mira)

        return self.criar_pagina("Câmera e captura",
                                 "Captura de imagens e alinhamento da câmera.", [s1, s2, s3])

    def pagina_zona(self):
        s1, l1 = self.secao("Acesso às zonas")
        self.chk_bloquear = QCheckBox("Bloquear edição")
        self.chk_bloquear.setChecked(True)
        self.chk_bloquear.toggled.connect(self.mudou_bloqueio)
        l1.addWidget(self.chk_bloquear)
        l1.addWidget(self.rotulo("Desmarque e informe a senha MURUIA para editar."))

        s2, l2 = self.secao("Cor da próxima zona")
        linha = QHBoxLayout()
        linha.setSpacing(8)
        self.grupo_cores = []
        for nome, hexa in CORES_ZONA:
            b = QPushButton()
            b.setCheckable(True)
            b.setToolTip(nome)
            b.setAccessibleName(nome)
            b.setFixedSize(28, 28)
            b.setStyleSheet(
                f"QPushButton {{ background:{hexa}; border:2px solid #ffffff; border-radius:14px;"
                f" padding:0; min-height:0; min-width:0; }}"
                f"QPushButton:checked {{ border:2px solid #111111; }}"
                f"QPushButton:hover {{ border:2px solid #9ca3af; }}")
            b.clicked.connect(lambda _, h=hexa: self.mudou_cor(h))
            linha.addWidget(b)
            self.grupo_cores.append((hexa, b))
        linha.addStretch()
        l2.addLayout(linha)
        self.grupo_cores[0][1].setChecked(True)
        l2.addWidget(self.rotulo("As cores identificam visualmente cada zona; qualquer zona gera o mesmo alerta."))

        s3, l3 = self.secao("Zonas cadastradas")
        self.lista_zonas = QListWidget()
        self.lista_zonas.setMaximumHeight(126)
        self.lista_zonas.currentRowChanged.connect(self.selecionar_zona)
        l3.addWidget(self.lista_zonas)

        self.btn_zona = QPushButton("Desenhar nova zona")
        self.btn_zona.setObjectName("btn_secondary")
        self.btn_zona.setCheckable(True)
        self.btn_zona.toggled.connect(self.alternar_modo_desenho)
        self.btn_aplicar_cor = QPushButton("Aplicar cor à zona selecionada")
        self.btn_aplicar_cor.setObjectName("btn_secondary")
        self.btn_aplicar_cor.clicked.connect(self.aplicar_cor_zona_selecionada)
        self.btn_zona_excluir = QPushButton("Excluir zona selecionada")
        self.btn_zona_excluir.setObjectName("btn_danger")
        self.btn_zona_excluir.clicked.connect(self.excluir_zona)
        l3.addWidget(self.btn_zona)
        l3.addWidget(self.btn_aplicar_cor)
        l3.addWidget(self.btn_zona_excluir)
        l3.addWidget(self.rotulo(
            "Desenhe um polígono: clique com o botão esquerdo para marcar os pontos e com o direito para concluir. "
            "Selecione uma zona na lista para mover ou ajustar seus vértices."
        ))
        self.controles_zona = [self.btn_zona, self.btn_aplicar_cor, self.btn_zona_excluir]
        return self.criar_pagina("Zona de perigo", "Crie, selecione e edite múltiplas zonas.", [s1, s2, s3])

    def pagina_calibracao(self):
        s1, l1 = self.secao("Fator de escala")
        linha = QHBoxLayout()
        linha.addWidget(QLabel("Fator (mm por pixel)"))
        linha.addStretch()
        self.spin_fator = QDoubleSpinBox()
        self.spin_fator.setDecimals(4)
        self.spin_fator.setRange(0.0, 100000.0)
        self.spin_fator.setSingleStep(0.1)
        self.spin_fator.setSpecialValueText("não calibrado")
        self.spin_fator.setFixedWidth(120)
        self.spin_fator.valueChanged.connect(self.atualizar_info_zona)
        linha.addWidget(self.spin_fator)
        l1.addLayout(linha)

        linha = QHBoxLayout()
        linha.addWidget(QLabel("Exibir medidas em"))
        linha.addStretch()
        self.combo_un = QComboBox()
        self.combo_un.addItems(["m", "cm", "mm"])
        self.combo_un.setFixedWidth(84)
        self.combo_un.currentTextChanged.connect(self.atualizar_info_zona)
        linha.addWidget(self.combo_un)
        l1.addLayout(linha)

        btn = QPushButton("Calibrar por referência…")
        btn.setObjectName("btn_secondary")
        btn.clicked.connect(self.abrir_calibracao)
        l1.addWidget(btn)

        return self.criar_pagina("Calibração", "Converta pixels em medidas reais.", [s1])

    def criar_area_video(self):
        cont = QWidget()
        cont.setObjectName("centro")
        cl = QVBoxLayout(cont)
        cl.setContentsMargins(14, 14, 14, 14)

        card = QFrame()
        card.setObjectName("cartao")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(12, 10, 12, 12)
        lay.setSpacing(8)

        topo = QHBoxLayout()
        t = QLabel("VISUALIZAÇÃO AO VIVO")
        t.setObjectName("secao_titulo")
        self.lbl_dica_video = QLabel("")
        self.lbl_dica_video.setObjectName("dica")
        topo.addWidget(t)
        topo.addStretch()
        topo.addWidget(self.lbl_dica_video)
        lay.addLayout(topo)

        lay.addWidget(self.view, 1)

        self.alert_label = QLabel()
        self.alert_label.setAlignment(Qt.AlignCenter)
        self.alert_label.setFixedHeight(44)
        lay.addWidget(self.alert_label)

        cl.addWidget(card)
        return cont

    def criar_painel_status(self):
        scroll = QScrollArea()
        scroll.setObjectName("scroll_status")
        scroll.setFixedWidth(self.LARG_STATUS)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        conteudo = QWidget()
        conteudo.setObjectName("painel_status")
        col = QVBoxLayout(conteudo)
        col.setContentsMargins(12, 12, 12, 12)
        col.setSpacing(12)
        scroll.setWidget(conteudo)

        # Ocupação
        c, lay = self.cartao("Ocupação")
        grade = QGridLayout()
        grade.setSpacing(8)
        k1, self.val_pessoas = self.kpi("PESSOAS NA IMAGEM", "—")
        k2, self.val_zona_n = self.kpi("PESSOAS NA ZONA", "0")
        k3, self.val_alertas = self.kpi("ALERTAS NA SESSÃO", "0")
        k4, self.val_estado = self.kpi("ÁREA DE PERIGO", "SEM ZONA")
        self.val_zona_n.setProperty("estado", "ok")
        self.val_estado.setObjectName("kpi_valor_pequeno")
        grade.addWidget(k1, 0, 0)
        grade.addWidget(k2, 0, 1)
        grade.addWidget(k3, 1, 0)
        grade.addWidget(k4, 1, 1)
        lay.addLayout(grade)
        col.addWidget(c)

        # Desempenho
        c, lay = self.cartao("Desempenho")
        l1, self.val_fps = self.linha_info("FPS atual")
        lay.addLayout(l1)
        self.grafico_fps = GraficoLinha("#16a34a", 30)
        lay.addWidget(self.grafico_fps)
        l2, self.val_fps_medio = self.linha_info("FPS médio")
        lay.addLayout(l2)
        lay.addSpacing(4)
        l3, self.val_latencia = self.linha_info("Latência de inferência")
        lay.addLayout(l3)
        self.grafico_lat = GraficoLinha("#404040", 50)
        lay.addWidget(self.grafico_lat)
        col.addWidget(c)

        # Imagem e escala
        c, lay = self.cartao("Imagem e escala")
        l1, self.val_resolucao = self.linha_info("Resolução")
        l2, self.val_pixels = self.linha_info("Total de pixels")
        l3, self.val_campo = self.linha_info("Campo de visão")
        l4, self.val_zona_info = self.linha_info("Zona de perigo", "não definida")
        l5, self.val_zona_real = self.linha_info("Zona (medida max)", "—")
        for l in (l1, l2, l3, l4, l5):
            lay.addLayout(l)
        col.addWidget(c)

        # Sessão
        c, lay = self.cartao("Sessão")
        l1, self.val_tempo = self.linha_info("Tempo ativo", "00:00:00")
        l2, self.val_capturas = self.linha_info("Capturas salvas", "0")
        lay.addLayout(l1)
        lay.addLayout(l2)
        col.addWidget(c)

        # Eventos
        c, lay = self.cartao("Eventos recentes")
        self.lista_eventos = QListWidget()
        self.lista_eventos.setMinimumHeight(150)
        lay.addWidget(self.lista_eventos)
        col.addWidget(c)

        col.addStretch()
        return scroll

    def criar_rodape(self):
        barra = QFrame()
        barra.setObjectName("rodape")
        barra.setFixedHeight(28)
        lay = QHBoxLayout(barra)
        lay.setContentsMargins(16, 0, 16, 0)
        self.status_label = QLabel("Pronto para iniciar")
        self.status_label.setObjectName("rodape_texto")
        self.lbl_relogio = QLabel("")
        self.lbl_relogio.setObjectName("rodape_texto")
        lay.addWidget(self.status_label)
        lay.addStretch()
        lay.addWidget(self.lbl_relogio)
        return barra

    def rodando(self):
        return self.video_thread is not None and self.video_thread.isRunning()

    def atualizar_botoes(self):
        r = self.rodando()
        self.act_iniciar.setEnabled(not r)
        self.btn_iniciar.setEnabled(not r)
        self.act_pausar.setEnabled(r)
        self.btn_pausar.setEnabled(r)
        self.act_parar.setEnabled(r)
        self.btn_parar.setEnabled(r)
        self.spin_camera.setEnabled(not r)
        txt = "Retomar" if self.pausado else "Pausar"
        self.act_pausar.setText(txt)
        self.btn_pausar.setText(txt)
        self.act_pausar.setIcon(icone("play" if self.pausado else "pause"))
        tem_img = self.ultima_imagem is not None
        self.act_capturar.setEnabled(tem_img)
        self.btn_capturar_painel.setEnabled(tem_img)

    def iniciar_stream(self):
        if self.rodando():
            return
        self.pausado = False
        self.total_alertas = 0
        self.val_alertas.setText("0")
        self.fps_hist = []
        self.grafico_fps.limpar()
        self.grafico_lat.limpar()
        self.definir_badge(self.camera_badge, "● CONECTANDO CÂMERA", "warning")
        self.definir_badge(self.analysis_badge, "ANÁLISE INICIANDO", "neutral")

        self.video_thread = VideoThread(
            camera_source=self.spin_camera.value(),
            model_path=self.MODEL_PATH,
            zonas=self.zonas,
            confianca=self.p_conf.valor() / 100.0,
        )
        t = self.video_thread
        t.frame_signal.connect(self.atualizar_frame)
        t.status_signal.connect(self.atualizar_status)
        t.alert_signal.connect(self.alerta_visual)
        t.metrics_signal.connect(self.atualizar_metricas)
        t.pessoas_zona_signal.connect(self.atualizar_pessoas_zona)
        t.finished.connect(self.thread_finalizada)
        t.start()
        self.inicio_sessao = datetime.now()
        self.registrar_evento("Monitoramento iniciado")
        self.atualizar_botoes()

    def pausar_stream(self):
        if not self.rodando():
            return
        if self.pausado:
            self.video_thread.resume()
            self.pausado = False
            self.definir_badge(self.analysis_badge, "ANÁLISE ATIVA", "ok")
            self.registrar_evento("Monitoramento retomado")
        else:
            self.video_thread.pause()
            self.pausado = True
            self.definir_badge(self.analysis_badge, "ANÁLISE PAUSADA", "warning")
            self.registrar_evento("Monitoramento pausado")
        self.atualizar_botoes()

    def parar_stream(self):
        if self.rodando():
            self.video_thread.stop()
            self.registrar_evento("Monitoramento encerrado pelo operador")
        self.thread_finalizada()

    def thread_finalizada(self):
        self.pausado = False
        self.definir_badge(self.camera_badge, "● CÂMERA OFFLINE", "danger")
        self.definir_badge(self.analysis_badge, "ANÁLISE PARADA", "neutral")
        self.zona_em_alerta = False
        self.view.alerta = False
        self.view.update()
        self.val_pessoas.setText("—")
        self.val_fps.setText("—")
        self.val_latencia.setText("—")
        self.atualizar_pessoas_zona(0)
        self.atualizar_barra_alerta()
        self.atualizar_botoes()

    def mudou_confianca(self, v):
        if self.rodando():
            self.video_thread.definir_confianca(v / 100.0)

    def atualizar_frame(self, imagem):
        self.ultima_imagem = imagem
        self.view.set_frame(imagem)
        res = (imagem.width(), imagem.height())
        if res != self._res:
            self._res = res
            self.val_resolucao.setText(f"{res[0]} × {res[1]} px")
            total = res[0] * res[1]
            self.val_pixels.setText(f"{total:,}".replace(",", ".") + f"  ({total / 1e6:.2f} MP)")
            self.atualizar_info_zona()
            self.atualizar_botoes()

    def atualizar_status(self, msg):
        self.status(msg)
        if "Câmera conectada" in msg:
            self.definir_badge(self.camera_badge, "● CÂMERA ONLINE", "ok")
            self.definir_badge(self.analysis_badge, "ANÁLISE ATIVA", "ok")
            self.registrar_evento("Câmera conectada")
        elif msg.startswith("Erro"):
            self.registrar_evento(msg)

    def atualizar_metricas(self, fps, pessoas, inferencia_ms):
        self.val_pessoas.setText(str(pessoas))
        self.val_fps.setText(f"{fps:.1f}")
        self.val_latencia.setText(f"{inferencia_ms:.0f} ms")
        self.grafico_fps.adicionar(fps)
        self.grafico_lat.adicionar(inferencia_ms)
        self.fps_hist.append(fps)
        self.val_fps_medio.setText(f"{sum(self.fps_hist) / len(self.fps_hist):.1f}")

    def atualizar_pessoas_zona(self, n):
        self.val_zona_n.setText(str(n))
        self.val_zona_n.setProperty("estado", "perigo" if n > 0 else "ok")
        self.repolir(self.val_zona_n)

    def alerta_visual(self, ativo):
        if ativo and not self.zona_em_alerta:
            self.total_alertas += 1
            self.val_alertas.setText(str(self.total_alertas))
            self.registrar_evento("ALERTA: pessoa na área de perigo")
        elif not ativo and self.zona_em_alerta:
            self.registrar_evento("Área de perigo liberada")
        self.zona_em_alerta = ativo
        self.view.alerta = ativo
        self.view.update()
        self.atualizar_barra_alerta()

    @staticmethod
    def _area_poligono(pontos):
        soma = 0.0
        for i, (x1, y1) in enumerate(pontos):
            x2, y2 = pontos[(i + 1) % len(pontos)]
            soma += x1 * y2 - x2 * y1
        return soma / 2.0

    @classmethod
    def _normalizar_registro_zona(cls, bruto, indice=0):
        cor = "#dc2626"
        vertices = bruto
        if (isinstance(bruto, (tuple, list)) and len(bruto) == 2
                and isinstance(bruto[1], str)
                and isinstance(bruto[0], (tuple, list))):
            vertices, cor = bruto[0], bruto[1]
        elif isinstance(bruto, dict):
            cor = bruto.get("cor", bruto.get("color", cor))
            vertices = bruto.get("vertices")
            if vertices is None and all(k in bruto for k in ("centro_x", "centro_y", "largura", "altura")):
                cx, cy = float(bruto["centro_x"]), float(bruto["centro_y"])
                w, h = float(bruto["largura"]), float(bruto["altura"])
                ang = math.radians(float(bruto.get("angulo", 0.0)))
                c, sn = math.cos(ang), math.sin(ang)
                vertices = [[cx + dx*c - dy*sn, cy + dx*sn + dy*c]
                            for dx, dy in ((-w/2, -h/2), (w/2, -h/2),
                                           (w/2, h/2), (-w/2, h/2))]
        if vertices is None:
            return None
        if isinstance(vertices, (list, tuple)) and len(vertices) in (4, 5) and all(
            isinstance(v, (int, float)) for v in vertices
        ):
            vals = [float(v) for v in vertices]
            if len(vals) == 4:
                x1, y1, x2, y2 = vals
                vertices = [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]
            else:
                cx, cy, w, h, angulo = vals
                ang = math.radians(angulo)
                c, sn = math.cos(ang), math.sin(ang)
                vertices = [[cx + dx*c - dy*sn, cy + dx*sn + dy*c]
                            for dx, dy in ((-w/2, -h/2), (w/2, -h/2),
                                           (w/2, h/2), (-w/2, h/2))]
        try:
            pontos = [(float(p[0]), float(p[1])) for p in vertices]
        except (TypeError, ValueError, IndexError):
            return None
        if len(pontos) < 3 or any(
            not (math.isfinite(x) and math.isfinite(y) and 0 <= x <= 1 and 0 <= y <= 1)
            for x, y in pontos
        ) or abs(cls._area_poligono(pontos)) < 0.0005:
            return None
        qcor = QColor(str(cor))
        if not qcor.isValid():
            cor = "#dc2626"
        else:
            cor = qcor.name()
        return (pontos, cor)

    def carregar_zonas(self):
        """Lê o novo formato de várias zonas e migra o JSON antigo de zona única."""
        try:
            dados = json.loads(self.ZONA_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, AttributeError):
            return []
        if isinstance(dados, dict) and isinstance(dados.get("zonas"), list):
            brutas = dados["zonas"]
        elif isinstance(dados, dict) and "zona" in dados and dados["zona"] is not None:
            brutas = [dados["zona"]]
        elif isinstance(dados, list):
            brutas = dados
        else:
            return []
        resultado = []
        for i, bruto in enumerate(brutas):
            zona = self._normalizar_registro_zona(bruto, i)
            if zona is not None:
                resultado.append(zona)
        return resultado

    def salvar_zonas(self):
        dados = {
            "versao": 2,
            "zonas": [
                {"nome": f"Zona {i + 1}", "cor": cor,
                 "vertices": [[float(x), float(y)] for x, y in vertices]}
                for i, (vertices, cor) in enumerate(self.zonas)
            ],
        }
        temporario = self.ZONA_PATH.with_suffix(".tmp")
        try:
            self.ZONA_PATH.parent.mkdir(parents=True, exist_ok=True)
            temporario.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
            temporario.replace(self.ZONA_PATH)
            return True
        except OSError as e:
            self.status(f"Não foi possível salvar as zonas: {e}")
            return False

    def atualizar_lista_zonas(self):
        if not hasattr(self, "lista_zonas"):
            return
        self.lista_zonas.blockSignals(True)
        self.lista_zonas.clear()
        nomes = {hexa: nome for nome, hexa in CORES_ZONA}
        for i, (_, cor) in enumerate(self.zonas):
            item = QListWidgetItem(f"Zona {i + 1} — {nomes.get(cor, cor)}")
            item.setForeground(QColor(cor))
            self.lista_zonas.addItem(item)
        if 0 <= self.zona_selecionada_idx < len(self.zonas):
            self.lista_zonas.setCurrentRow(self.zona_selecionada_idx)
        else:
            self.lista_zonas.setCurrentRow(-1)
        self.lista_zonas.blockSignals(False)

    def atualizar_estado_edicao_zonas(self):
        if not hasattr(self, "chk_bloquear"):
            return
        bloqueada = not self.edicao_zona_liberada
        self.view.bloqueada = bloqueada
        self.chk_bloquear.blockSignals(True)
        self.chk_bloquear.setChecked(bloqueada)
        self.chk_bloquear.setText(
            "Bloquear edição" if bloqueada else "Edição liberada"
        )
        self.chk_bloquear.blockSignals(False)
        tem_selecionada = 0 <= self.zona_selecionada_idx < len(self.zonas)
        for _, botao in getattr(self, "grupo_cores", []):
            botao.setEnabled(not bloqueada)
        self.btn_zona.setEnabled(not bloqueada)
        self.btn_aplicar_cor.setEnabled(not bloqueada and tem_selecionada)
        self.btn_zona_excluir.setEnabled(not bloqueada and tem_selecionada)
        self.lista_zonas.setEnabled(True)
        self.view.update()

    def mudou_bloqueio(self, bloqueada):
        if not bloqueada:
            senha, ok = QInputDialog.getText(
                self, "Desbloquear edição das zonas", "Digite a senha do operador:", QLineEdit.Password
            )
            if not ok or senha != self.SENHA_ZONA:
                QMessageBox.warning(self, "Acesso negado", "Senha incorreta ou operação cancelada.")
                self.edicao_zona_liberada = False
                self.atualizar_estado_edicao_zonas()
                return
            self.edicao_zona_liberada = True
            self.status("Edição das zonas liberada")
        else:
            self.edicao_zona_liberada = False
            self.btn_zona.setChecked(False)
            self.view.definir_modo_desenho(False)
            self.status("Edição das zonas bloqueada")
        self.atualizar_estado_edicao_zonas()

    def selecionar_zona(self, indice):
        if indice < -1 or indice >= len(self.zonas):
            return
        self.zona_selecionada_idx = indice
        if hasattr(self, "lista_zonas") and self.lista_zonas.currentRow() != indice:
            self.lista_zonas.blockSignals(True)
            self.lista_zonas.setCurrentRow(indice)
            self.lista_zonas.blockSignals(False)
        if hasattr(self, "view"):
            self.view.set_zonas(self.zonas, indice)
        if hasattr(self, "btn_aplicar_cor"):
            self.atualizar_estado_edicao_zonas()
            self.atualizar_info_zona()

    def atualizar_barra_alerta(self):
        if not self.zonas:
            txt, obj, est, estado = "SEM ZONA DE PERIGO DEFINIDA", "alert_none", "SEM ZONA", "neutro"
        elif self.zona_em_alerta:
            txt, obj, est, estado = ("ALERTA  •  PESSOA EM UMA ÁREA DE PERIGO", "alert_active",
                                     "OCUPADA", "perigo")
        else:
            txt, obj, est, estado = ("ZONAS SEGURAS  •  NENHUMA PESSOA NAS ÁREAS DE PERIGO",
                                     "alert_safe", "LIVRE", "ok")
        self.alert_label.setText(txt)
        self.alert_label.setObjectName(obj)
        self.repolir(self.alert_label)
        self.val_estado.setText(est)
        self.val_estado.setProperty("estado", estado)
        self.repolir(self.val_estado)

    def aplicar_zonas(self, zonas, persistir=True):
        normalizadas = []
        for i, bruto in enumerate(zonas or []):
            zona = self._normalizar_registro_zona(bruto, i)
            if zona is not None:
                normalizadas.append(zona)
        self.zonas = normalizadas
        if not self.zonas:
            self.zona_selecionada_idx = -1
        elif not (0 <= self.zona_selecionada_idx < len(self.zonas)):
            self.zona_selecionada_idx = len(self.zonas) - 1
        self.view.set_zonas(self.zonas, self.zona_selecionada_idx)
        if self.rodando():
            self.video_thread.definir_zonas(self.zonas)
        if persistir:
            self.salvar_zonas()
            self.atualizar_lista_zonas()
        self.atualizar_info_zona()
        self.atualizar_estado_edicao_zonas()
        self.atualizar_barra_alerta()

    def ao_zona_criada(self, zona):
        if not self.edicao_zona_liberada:
            return
        criada = self._normalizar_registro_zona(zona)
        if criada is None:
            self.status("Zona inválida: desenhe um polígono com área válida")
            return
        self.zonas.append(criada)
        self.zona_selecionada_idx = len(self.zonas) - 1
        self.view.cor = self.cor_nova_zona
        self.view.set_zonas(self.zonas, self.zona_selecionada_idx)
        self.btn_zona.setChecked(False)
        self.salvar_zonas()
        self.atualizar_lista_zonas()
        self.atualizar_estado_edicao_zonas()
        if self.rodando():
            self.video_thread.definir_zonas(self.zonas)
        self.atualizar_info_zona()
        self.atualizar_barra_alerta()
        self.status(f"Zona {len(self.zonas)} criada e salva")
        self.registrar_evento(f"Zona {len(self.zonas)} criada")

    def mudou_cor(self, hexa):
        self.cor_nova_zona = hexa
        self.view.cor = hexa
        for h, botao in self.grupo_cores:
            botao.setChecked(h == hexa)
        nome = next((nome for nome, cor in CORES_ZONA if cor == hexa), hexa)
        self.status(f"Cor escolhida para a próxima zona: {nome}")

    def aplicar_cor_zona_selecionada(self):
        if not self.edicao_zona_liberada or not (0 <= self.zona_selecionada_idx < len(self.zonas)):
            return
        i = self.zona_selecionada_idx
        pontos, _ = self.zonas[i]
        self.zonas[i] = (pontos, self.cor_nova_zona)
        self.aplicar_zonas(self.zonas, persistir=True)
        self.registrar_evento(f"Cor atualizada na zona {i + 1}")
        self.status(f"Cor da zona {i + 1} atualizada e salva")

    def alternar_modo_desenho(self, ativo):
        if ativo and not self.edicao_zona_liberada:
            self.status("Desbloqueie a edição das zonas com a senha MURUIA")
            self.btn_zona.blockSignals(True)
            self.btn_zona.setChecked(False)
            self.btn_zona.blockSignals(False)
            return
        if ativo and self.ultima_imagem is None:
            self.status("Inicie o monitoramento para desenhar a zona na imagem")
            self.btn_zona.blockSignals(True)
            self.btn_zona.setChecked(False)
            self.btn_zona.blockSignals(False)
            return
        self.view.cor = self.cor_nova_zona
        self.view.definir_modo_desenho(ativo)
        if ativo:
            self.status("Esquerdo: adiciona ponto | Direito: fecha e salva a nova zona")

    def excluir_zona(self):
        i = self.zona_selecionada_idx
        if not self.edicao_zona_liberada or not (0 <= i < len(self.zonas)):
            return
        self.btn_zona.setChecked(False)
        removida = i + 1
        self.zonas.pop(i)
        self.zona_selecionada_idx = min(i, len(self.zonas) - 1)
        self.zona_em_alerta = False if not self.zonas else self.zona_em_alerta
        self.view.alerta = self.zona_em_alerta
        self.view.set_zonas(self.zonas, self.zona_selecionada_idx)
        if self.rodando():
            self.video_thread.definir_zonas(self.zonas)
        self.salvar_zonas()
        self.atualizar_lista_zonas()
        self.atualizar_estado_edicao_zonas()
        self.atualizar_pessoas_zona(0)
        self.atualizar_info_zona()
        self.atualizar_barra_alerta()
        self.registrar_evento(f"Zona {removida} excluída")
        self.status("Zona selecionada excluída; alterações salvas")

    def formatar_dist(self, px):
        fator = self.spin_fator.value()
        if fator <= 0:
            return None
        mm = px * fator
        un = self.combo_un.currentText()
        if un == "m":
            return f"{mm / 1000:.2f} m"
        if un == "cm":
            return f"{mm / 10:.1f} cm"
        return f"{mm:.0f} mm"

    def atualizar_info_zona(self, *_):
        tem = bool(self.zonas)
        if self.ultima_imagem is None:
            self.val_campo.setText("—")
            self.val_zona_info.setText("não definida" if not tem else f"{len(self.zonas)} zona(s)")
            self.val_zona_real.setText("—")
            return

        W, H = self.ultima_imagem.width(), self.ultima_imagem.height()
        a, b = self.formatar_dist(W), self.formatar_dist(H)
        self.val_campo.setText(f"{a} × {b}" if a else "não calibrado")
        if not tem:
            self.val_zona_info.setText("não definida")
            self.val_zona_real.setText("—")
            return

        self.val_zona_info.setText(f"{len(self.zonas)} zona(s) cadastrada(s)")
        if not (0 <= self.zona_selecionada_idx < len(self.zonas)):
            self.val_zona_real.setText("selecione uma zona")
            return
        pontos = self.zonas[self.zona_selecionada_idx][0]
        xs = [p[0] * W for p in pontos]
        ys = [p[1] * H for p in pontos]
        wp, hp = max(xs) - min(xs), max(ys) - min(ys)
        da, db = self.formatar_dist(wp), self.formatar_dist(hp)
        self.val_zona_real.setText(f"Zona {self.zona_selecionada_idx + 1}: {da} × {db}" if da else "não calibrado")

    def abrir_calibracao(self):
        dlg = DialogoCalibracao(self)
        if dlg.exec_() == QDialog.Accepted:
            self.spin_fator.setValue(dlg.fator_mm_por_px())
            self.registrar_evento(f"Calibração aplicada: {dlg.fator_mm_por_px():.4f} mm/px")

    def mudou_enquadramento(self, *_):
        self.view.set_enquadramento(self.p_zoom.valor() / 100.0,
                                    self.p_pan_x.valor(), self.p_pan_y.valor())

    def resetar_enquadramento(self):
        self.p_zoom.definir(100)
        self.p_pan_x.definir(0)
        self.p_pan_y.definir(0)
        self.chk_grade.setChecked(False)
        self.chk_mira.setChecked(False)
        self.mudou_enquadramento()

    def capturar_imagem(self):
        if self.ultima_imagem is None:
            self.status("Nenhuma imagem disponível para capturar")
            return
        img = self.ultima_imagem.copy()
        
        if self.chk_cap_zona.isChecked() and self.zonas:
            W, H = img.width(), img.height()
            p = QPainter(img)
            p.setRenderHint(QPainter.Antialiasing)
            for vertices, cor_hex in self.zonas:
                pts = [(x * W, y * H) for x, y in vertices]
                cor = QColor(cor_hex)
                fill = QColor(cor)
                fill.setAlpha(45)
                borda = QColor(cor)
                borda.setAlpha(190)
                p.setPen(QPen(borda, max(1.2, W / 700.0)))
                p.setBrush(QBrush(fill))
                p.drawPolygon(QPolygonF([QPointF(x, y) for x, y in pts]))
            p.end()

        ext = self.combo_formato.currentText().lower()
        os.makedirs(self.PASTA_CAPTURAS, exist_ok=True)
        nome = datetime.now().strftime(f"vigia_%Y%m%d_%H%M%S.{ext}")
        caminho = os.path.join(self.PASTA_CAPTURAS, nome)
        if img.save(caminho, None, 95):
            self.total_capturas += 1
            self.val_capturas.setText(str(self.total_capturas))
            self.registrar_evento(f"Imagem capturada: {nome}")
            self.status(f"Imagem salva em {os.path.abspath(caminho)}")
        else:
            self.status("Falha ao salvar a imagem")

    def abrir_pasta_capturas(self):
        os.makedirs(self.PASTA_CAPTURAS, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.abspath(self.PASTA_CAPTURAS)))

    def tick(self):
        agora = datetime.now()
        self.lbl_relogio.setText(agora.strftime("%d/%m/%Y  %H:%M:%S"))
        if self.rodando() and self.inicio_sessao is not None and not self.pausado:
            s = int((agora - self.inicio_sessao).total_seconds())
            self.val_tempo.setText(f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}")
        hint = []
        if self.view.modo_desenho:
            hint.append("Clique Esquerdo: ponto • Clique Direito: fecha polígono")
        elif self.zonas:
            hint.append(f"{len(self.zonas)} zona(s) salva(s) • selecione uma na lista para editar")
        self.lbl_dica_video.setText("   ".join(hint))

    def alternar_tela_cheia(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def tecla_esc(self):
        if self.btn_zona.isChecked():
            self.btn_zona.setChecked(False)
        elif self.isFullScreen():
            self.showNormal()

    def closeEvent(self, event):
        if self.rodando():
            self.video_thread.stop()
        self.salvar_zonas()
        event.accept()

    def aplicar_tema(self):
        qss = """
        QMainWindow, QWidget#raiz, QWidget#centro, QWidget#painel_status { background:@FUNDO@; }
        QWidget { color:@TEXTO@; font-family:'Segoe UI', Arial, sans-serif; font-size:13px; }
        QLabel { background:transparent; }
        QToolTip { background:#111111; color:#ffffff; border:none; padding:4px 8px; }
        QFrame#linha_verde { background:@VERDE_LINHA@; border:none; }
        QFrame#linha_verde_suave { background:@VERDE_SUAVE@; border:none; }
        QFrame#barra_superior, QFrame#trilho, QWidget#flyout, QWidget#pagina,
        QWidget#conteudo_pagina, QFrame#rodape { background:@PAINEL@; }
        QLabel#app_titulo { font-size:19px; font-weight:800; letter-spacing:3px; color:#111111; }
        QLabel#app_subtitulo { font-size:11px; color:@MUTED@; }
        QToolButton#btn_menu { background:#000000; color:#ffffff; border:none; border-radius:10px;
                               font-size:11px; font-weight:600; }
        QToolButton#btn_menu:hover { background:#1f1f1f; }
        QToolButton#btn_menu::menu-indicator { image:none; width:0; }
        QToolButton#btn_barra { background:transparent; border:none; border-radius:8px;
                                font-size:10px; color:#404040; padding-top:2px; }
        QToolButton#btn_barra:hover { background:@FUNDO@; }
        QToolButton#btn_barra:disabled { color:#b9b9b9; }
        QLabel#badge { padding:7px 14px; border-radius:14px; font-size:11px; font-weight:700; }
        QLabel#badge[kind="ok"] { background:#dcfce7; color:#166534; }
        QLabel#badge[kind="danger"] { background:#fee2e2; color:#991b1b; }
        QLabel#badge[kind="warning"] { background:#fef3c7; color:#92400e; }
        QLabel#badge[kind="neutral"] { background:#e7e7e7; color:#525252; }
        QToolButton#btn_trilho { background:transparent; border:none; border-left:3px solid transparent;
                                 font-size:10px; color:#525252; padding:6px 0 4px 0; }
        QToolButton#btn_trilho:hover { background:#f5f5f5; }
        QToolButton#btn_trilho:checked { background:@VERDE_FUNDO@; color:@VERDE_ESC@;
                                         border-left:3px solid @VERDE@; font-weight:700; }
        QLabel#pagina_titulo { font-size:16px; font-weight:700; color:#111111; }
        QLabel#pagina_desc, QLabel#dica { font-size:11px; color:@MUTED@; }
        QLabel#secao_titulo { font-size:11px; font-weight:800; letter-spacing:1px; color:#404040;
                              border-left:3px solid @VERDE@; padding-left:8px; }
        QLabel#param_rotulo { color:#404040; }
        QLabel#info_chave { color:@MUTED@; }
        QLabel#info_valor { font-weight:700; color:#111111; }
        QFrame#cartao { background:@PAINEL@; border:1px solid @BORDA@; border-radius:8px; }
        QFrame#kpi { background:#fafafa; border:1px solid #e6e6e6; border-radius:8px; }
        QLabel#kpi_titulo { font-size:9px; font-weight:800; color:@MUTED@; }
        QLabel#kpi_valor { font-size:26px; font-weight:800; color:#111111; }
        QLabel#kpi_valor_pequeno { font-size:16px; font-weight:800; color:#111111; padding:5px 0; }
        QLabel#kpi_valor[estado="ok"], QLabel#kpi_valor_pequeno[estado="ok"] { color:@VERDE_HOVER@; }
        QLabel#kpi_valor[estado="perigo"], QLabel#kpi_valor_pequeno[estado="perigo"] { color:#dc2626; }
        QLabel#kpi_valor_pequeno[estado="neutro"] { color:#8a8a8a; }
        QLabel#alert_safe { background:#dcfce7; color:#166534; border-radius:8px; font-weight:800; }
        QLabel#alert_active { background:#dc2626; color:#ffffff; border-radius:8px; font-weight:800; }
        QLabel#alert_none { background:#ececec; color:#6b6b6b; border-radius:8px; font-weight:700; }
        QPushButton { border-radius:6px; font-weight:600; padding:8px 12px; min-height:18px; }
        QPushButton#btn_primary { background:@VERDE@; color:#ffffff; border:none; min-height:22px; }
        QPushButton#btn_primary:hover { background:@VERDE_HOVER@; }
        QPushButton#btn_secondary { background:#ffffff; color:#1f1f1f; border:1px solid #cfcfcf; }
        QPushButton#btn_secondary:hover { background:#f5f5f5; }
        QPushButton#btn_secondary:checked { background:@VERDE_FUNDO@; color:@VERDE_ESC@; border:1px solid @VERDE@; }
        QPushButton#btn_danger { background:#ffffff; color:#b91c1c; border:1px solid #fca5a5; }
        QPushButton#btn_danger:hover { background:#fef2f2; }
        QPushButton#btn_dark { background:#111111; color:#ffffff; border:none; min-height:22px; }
        QPushButton#btn_dark:hover { background:#2b2b2b; }
        QPushButton#btn_ghost { background:transparent; color:#525252; border:1px dashed #c9c9c9; }
        QPushButton#btn_ghost:hover { color:@VERDE_ESC@; border-color:@VERDE@; background:@VERDE_FUNDO@; }
        QPushButton#btn_primary:disabled, QPushButton#btn_secondary:disabled,
        QPushButton#btn_danger:disabled, QPushButton#btn_dark:disabled {
            background:#f3f3f3; color:#a8a8a8; border:1px solid #e6e6e6; }
        QDoubleSpinBox, QSpinBox, QComboBox { background:#ffffff; border:1px solid #cfcfcf;
                                              border-radius:6px; padding:4px 8px; min-height:20px; }
        QDoubleSpinBox:focus, QSpinBox:focus, QComboBox:focus { border:1px solid @VERDE@; }
        QDoubleSpinBox:disabled, QSpinBox:disabled, QComboBox:disabled { background:#f5f5f5; color:#a8a8a8; }
        QComboBox::drop-down { border:none; width:22px; }
        QComboBox QAbstractItemView { background:#ffffff; border:1px solid #cfcfcf;
                                      selection-background-color:@VERDE_FUNDO@;
                                      selection-color:@VERDE_ESC@; }
        QCheckBox { spacing:8px; }
        QSlider::groove:horizontal { height:4px; background:#e0e0e0; border-radius:2px; }
        QSlider::sub-page:horizontal { background:@VERDE@; border-radius:2px; }
        QSlider::handle:horizontal { background:#ffffff; border:2px solid @VERDE@; width:12px; margin:-6px 0; border-radius:8px; }
        QSlider::sub-page:horizontal:disabled { background:#cfcfcf; }
        QSlider::handle:horizontal:disabled { border-color:#cfcfcf; }
        QListWidget { background:#fafafa; border:1px solid #e6e6e6; border-radius:6px; font-size:11px; }
        QListWidget::item { padding:4px 6px; }
        QScrollArea { background:transparent; border:none; }
        QScrollBar:vertical { background:transparent; width:8px; margin:0; }
        QScrollBar::handle:vertical { background:#cfcfcf; border-radius:4px; min-height:30px; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background:transparent; }
        QMenu { background:#ffffff; border:1px solid #d4d4d4; padding:4px; }
        QMenu::item { padding:7px 22px; border-radius:4px; }
        QMenu::item:selected { background:@VERDE_FUNDO@; color:@VERDE_ESC@; }
        QMenu::separator { height:1px; background:@VERDE_SUAVE@; margin:4px 6px; }
        QLabel#rodape_texto { font-size:11px; color:@MUTED@; }
        QDialog { background:#ffffff; }
        """
        for k, v in PALETA.items():
            qss = qss.replace(k, v)
        self.setStyleSheet(qss)

if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    janela = MainWindow()
    janela.show()
    sys.exit(app.exec_())

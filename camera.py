import cv2
import os
from ultralytics import YOLO

# Carrega o modelo de IA do GitHub (ele vai baixar um arquivo leve na primeira vez)
print("Carregando inteligência artificial...")
model = YOLO('yolov8n.pt') 

# Suas configurações da câmera Intelbras
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|stimeout;5000000"
SENHA_DISPOSITIVO = "MURUIA2026"
IP_CAMERA = "192.168.0.110"
RTSP_URL = f"rtsp://admin:{SENHA_DISPOSITIVO}@{IP_CAMERA}:554/cam/realmonitor?channel=1&subtype=1"

print("Conectando à câmera...")
cap = cv2.VideoCapture(RTSP_URL, cv2.CAP_FFMPEG)

if not cap.isOpened():
    print("Não foi possível conectar à câmera.")
else:
    print("Câmera conectada! Pressione 'q' na imagem para fechar.")
    while True:
        ret, frame = cap.read()
        if not ret:
            continue

        # A IA analisa o frame buscando apenas pessoas (classes=[0]) com 50% de confiança (conf=0.5)
        resultados = model(frame, classes=[0], conf=0.5, verbose=False)

        # Desenha os retângulos em volta das pessoas detectadas
        frame_anotado = resultados[0].plot()

        cv2.imshow("Monitoramento de Pessoas", frame_anotado)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

cap.release()
cv2.destroyAllWindows()

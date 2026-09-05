import asyncio
import websockets
import json
import urllib.request
import numpy as np
import cv2
import sqlite3
import os
from datetime import datetime

WS_URL    = "ws://192.168.0.19:8765/ws/sensing"
CAM_URL   = "http://192.168.0.9:8080/shot.jpg"
DB_PATH   = os.path.expanduser("~/Documents/RuView/_Domian/demo/data/pose_training.db")

# Calibración (de la sesión anterior)
A_X = [-1.46394702e-03, 2.48137988e-03, 2.05885625e+00]
A_Y = [-1.52530124e-03, -4.75273955e-04, 3.73407327e+00]

def px_to_metros(px_x, px_y):
    x = A_X[0]*px_x + A_X[1]*px_y + A_X[2]
    y = A_Y[0]*px_x + A_Y[1]*px_y + A_Y[2]
    return x, y

hog = cv2.HOGDescriptor()
hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

def init_db():
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS pose_pairs (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp    TEXT,
            cam_x_px     REAL,
            cam_y_px     REAL,
            pos_x_m      REAL,
            pos_y_m      REAL,
            csi_features TEXT
        )
    """)
    con.commit()
    return con

def detectar_persona():
    try:
        img_resp = urllib.request.urlopen(CAM_URL, timeout=2)
        img_array = np.array(bytearray(img_resp.read()), dtype=np.uint8)
        frame = cv2.imdecode(img_array, -1)
        boxes, weights = hog.detectMultiScale(frame, winStride=(8,8))
        if len(boxes) > 0:
            x, y, w, h = boxes[0]
            cx, cy = x + w/2, y + h/2
            return float(cx), float(cy)
    except Exception as e:
        pass
    return None

async def grabar_pares():
    con = init_db()
    cur = con.cursor()
    pares = 0

    print("🎥 Grabando pares CSI + posición cámara (calibrada)...")
    print(f"{'Hora':8} {'Pos X(m)':10} {'Pos Y(m)':10} {'Pares':8}")

    while True:
        try:
            async with websockets.connect(WS_URL, ping_interval=20, ping_timeout=10) as ws:
                while True:
                    try:
                        msg = await ws.recv()
                        data = json.loads(msg)
                        ts = datetime.now().isoformat()

                        pos = detectar_persona()
                        if pos:
                            cx_px, cy_px = pos
                            x_m, y_m = px_to_metros(cx_px, cy_px)
                            csi_features = json.dumps(data.get("node_features", []))

                            cur.execute("""
                                INSERT INTO pose_pairs 
                                (timestamp, cam_x_px, cam_y_px, pos_x_m, pos_y_m, csi_features)
                                VALUES (?,?,?,?,?,?)
                            """, (ts, cx_px, cy_px, x_m, y_m, csi_features))
                            con.commit()
                            pares += 1

                            print(f"{ts[11:19]:8} {x_m:10.2f} {y_m:10.2f} {pares:8}", end='\r')

                        await asyncio.sleep(1)

                    except websockets.exceptions.ConnectionClosed:
                        print("\n⚠️  WebSocket cerrado, reconectando...")
                        break

        except Exception as e:
            print(f"\nError de conexión: {e} — reintentando en 3s...")
            await asyncio.sleep(3)

asyncio.run(grabar_pares())
import asyncio
import websockets
import json
import numpy as np
import torch
import torch.nn as nn
from datetime import datetime

WS_URL     = "ws://192.168.0.8:8765/ws/sensing"
MODEL_DIR  = "/Users/cesarp/Documents/RuView/_Domian/demo/models/v1"

# Modelo
class CSIClassifier(nn.Module):
    def __init__(self, input_dim=56, hidden=128, num_classes=2):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden),
            nn.BatchNorm1d(hidden),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(hidden, 64),
            nn.ReLU(),
            nn.Linear(64, num_classes)
        )
    def forward(self, x): return self.net(x)

# Cargar modelo
model = CSIClassifier()
model.load_state_dict(torch.load(f"{MODEL_DIR}/domian_model.pt", map_location="cpu"))
model.eval()
mean = np.load(f"{MODEL_DIR}/domian_mean.npy")
std  = np.load(f"{MODEL_DIR}/domian_std.npy")

CLASES = {0: "present_still", 1: "present_moving"}

def predecir(amplitudes):
    x = np.array(amplitudes[:56], dtype=np.float32)
    x = (x - mean) / std
    with torch.no_grad():
        logits = model(torch.FloatTensor(x).unsqueeze(0))
        probs  = torch.softmax(logits, dim=1)[0]
        clase  = probs.argmax().item()
        conf   = probs[clase].item()
    return CLASES[clase], conf

async def escuchar():
    print("Conectando...")
    async with websockets.connect(WS_URL) as ws:
        print(f"{'Hora':8} {'Nodo':6} {'DOMIAN':16} {'Conf':6} {'RuView':16}")
        print("-" * 55)
        async for msg in ws:
            data = json.loads(msg)
            ts   = datetime.now().strftime("%H:%M:%S")
            clf  = data.get("classification", {})
            ruview_estado = clf.get("motion_level", "unknown")

            for node in data.get("nodes", []):
                amp = node.get("amplitude", [])
                if len(amp) >= 56:
                    domian_estado, conf = predecir(amp)
                    print(f"{ts:8} N{node['node_id']:<5} {domian_estado:16} {conf:.2f}   {ruview_estado}")

asyncio.run(escuchar())
"""Lógica pura (numpy/PIL/json) del etiquetador web. Sin Streamlit, para poder probarla aparte."""
from __future__ import annotations

import io
import json
import zipfile

import numpy as np
from PIL import Image

PALETTE = [(60, 180, 75), (220, 40, 40), (0, 120, 255), (128, 0, 128), (255, 255, 0),
           (139, 69, 19), (0, 200, 0), (255, 140, 0), (200, 200, 200), (255, 0, 255), (0, 255, 255), (0, 0, 255)]


def class_color(i: int) -> tuple:
    return PALETTE[i % len(PALETTE)]


def load_pack(src) -> dict:
    """src: ruta o bytes de un .zip creado con scripts/11_pack_for_labeling.py."""
    z = zipfile.ZipFile(io.BytesIO(src) if isinstance(src, (bytes, bytearray)) else src)
    manifest = json.loads(z.read("manifest.json"))
    images, segs = {}, {}
    for it in manifest["images"]:
        s = it["stem"]
        images[s] = np.array(Image.open(io.BytesIO(z.read(f"images/{s}.jpg"))).convert("RGB"))
        segs[s] = np.load(io.BytesIO(z.read(f"segments/{s}.npz")))["seg"].astype(np.int32)
        if segs[s].shape != images[s].shape[:2]:
            raise ValueError(f"{s}: imagen y segmentos de distinto tamaño")
    start = json.loads(z.read("labels_start.json")) if "labels_start.json" in z.namelist() else {}
    return {"manifest": manifest, "images": images, "segs": segs, "labels_start": start}


def boundaries(seg: np.ndarray) -> np.ndarray:
    b = np.zeros(seg.shape, bool)
    d = seg[:, 1:] != seg[:, :-1]
    b[:, 1:] |= d
    b[:, :-1] |= d
    d = seg[1:, :] != seg[:-1, :]
    b[1:, :] |= d
    b[:-1, :] |= d
    return b


def centroids(seg: np.ndarray) -> np.ndarray:
    """(N+1, 2) con (x, y) del centroide de cada ID de segmento (fila 0 sin uso)."""
    n = int(seg.max()) + 1
    ys, xs = np.indices(seg.shape)
    cnt = np.bincount(seg.ravel(), minlength=n).astype(np.float64)
    cnt[cnt == 0] = 1
    cx = np.bincount(seg.ravel(), weights=xs.ravel(), minlength=n) / cnt
    cy = np.bincount(seg.ravel(), weights=ys.ravel(), minlength=n) / cnt
    return np.stack([cx, cy], axis=1)


def render(img: np.ndarray, seg: np.ndarray, bnd: np.ndarray, labels: dict, classes: list[str],
           show_bnd: bool = True, alpha: float = 0.45, visible: set | None = None) -> np.ndarray:
    """visible: conjunto de clases a pintar (None = todas; conjunto vacío = ninguna, solo foto + contornos)."""
    out = img.astype(np.float32)
    if labels:
        lut = np.zeros((int(seg.max()) + 1, 3), np.float32)
        has = np.zeros(int(seg.max()) + 1, bool)
        for sid, cls in labels.items():
            sid = int(sid)
            if cls in classes and sid < len(has) and (visible is None or cls in visible):
                lut[sid] = class_color(classes.index(cls))
                has[sid] = True
        m = has[seg]
        out[m] = (1 - alpha) * out[m] + alpha * lut[seg][m]
    if show_bnd:
        out[bnd] = 0.35 * out[bnd] + 0.65 * np.array([255, 255, 0], np.float32)
    return out.astype(np.uint8)


def segment_at(seg: np.ndarray, x: float, y: float, disp_w: float, disp_h: float) -> int:
    h, w = seg.shape
    px = int(np.clip(x * w / disp_w, 0, w - 1))
    py = int(np.clip(y * h / disp_h, 0, h - 1))
    return int(seg[py, px])


def segments_in_rect(cent: np.ndarray, x1, y1, x2, y2, disp_w, disp_h, seg_shape) -> list[int]:
    h, w = seg_shape
    sx, sy = w / disp_w, h / disp_h
    xa, xb = sorted((x1 * sx, x2 * sx))
    ya, yb = sorted((y1 * sy, y2 * sy))
    ids = np.nonzero((cent[:, 0] >= xa) & (cent[:, 0] <= xb) & (cent[:, 1] >= ya) & (cent[:, 1] <= yb))[0]
    return [int(i) for i in ids if i > 0]


def apply_click(value: dict, seg: np.ndarray, cent: np.ndarray, drag_min_px: float = 6) -> list[int]:
    """Convierte la salida del componente (clic o arrastre) en la lista de IDs de segmento afectados."""
    if value is None:
        return []
    dw, dh = value["width"], value["height"]
    if "x1" in value:
        if abs(value["x2"] - value["x1"]) < drag_min_px and abs(value["y2"] - value["y1"]) < drag_min_px:
            sid = segment_at(seg, value["x1"], value["y1"], dw, dh)
            return [sid] if sid > 0 else []
        return segments_in_rect(cent, value["x1"], value["y1"], value["x2"], value["y2"], dw, dh, seg.shape)
    sid = segment_at(seg, value["x"], value["y"], dw, dh)
    return [sid] if sid > 0 else []


def merge_start_labels(start: dict, pack: dict) -> dict:
    """Etiquetas iniciales válidas para este paquete (descarta fotos/segmentos/clases desconocidos)."""
    names = {it["name"]: it["stem"] for it in pack["manifest"]["images"]}
    classes = pack["manifest"]["classes"]
    out = {n: {} for n in names}
    skipped = 0
    for name, segs in start.items():
        if name not in names:
            skipped += len(segs)
            continue
        mx = int(pack["segs"][names[name]].max())
        for sid, cls in segs.items():
            if cls in classes and 0 < int(sid) <= mx:
                out[name][str(int(sid))] = cls
            else:
                skipped += 1
    return out, skipped


def labels_to_json(labels: dict) -> str:
    """Mismo formato que workspace/labels.json: {foto: {id_segmento: clase}} (solo fotos con etiquetas)."""
    return json.dumps({k: v for k, v in labels.items() if v}, indent=2, ensure_ascii=False)

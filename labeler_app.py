"""Etiquetador web de segmentos (Streamlit). Para que otras personas generen el JSON de etiquetas.

Ejecutar:   streamlit run app/labeler_app.py
Opcional:   definir BIOCRUST_PACK=ruta\\labeling_pack.zip para que abra ese paquete solo.
Requiere:   pip install streamlit streamlit-image-coordinates numpy pillow
Uso:        elegir clase en la barra lateral -> clic en un segmento, o ARRASTRAR un rectángulo para asignar la clase
            a todos los segmentos cuyo centro cae dentro. Al terminar: "Descargar etiquetas" y enviar el JSON.
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path

import streamlit as st
from PIL import Image
from streamlit_image_coordinates import streamlit_image_coordinates

import labeler_core as core

st.set_page_config(page_title="Etiquetador biocrust", layout="wide")


@st.cache_data(show_spinner="Abriendo paquete...")
def _load(data: bytes | str):
    return core.load_pack(data)


@st.cache_data(show_spinner=False)
def _bnd_and_cent(pack_key: str, stem: str, seg_bytes: bytes, shape: tuple):
    import numpy as np
    seg = np.frombuffer(seg_bytes, dtype=np.int32).reshape(shape)
    return core.boundaries(seg), core.centroids(seg)


def get_pack():
    path = os.environ.get("BIOCRUST_PACK")
    up = st.sidebar.file_uploader("Paquete de etiquetado (.zip)", type=["zip"])
    if up is not None:
        return _load(up.getvalue()), f"{up.name}:{up.size}"
    if path and Path(path).exists():
        return _load(path), path
    return None, None


def main():
    st.sidebar.title("Etiquetador biocrust")
    who = st.sidebar.text_input("Tu nombre", value=st.session_state.get("who", ""), key="who")
    pack, pack_key = get_pack()
    if pack is None:
        st.info("Sube el paquete .zip (generado con `scripts/11_pack_for_labeling.py`) en la barra lateral.")
        return
    man = pack["manifest"]
    classes = man["classes"]
    items = man["images"]
    if st.session_state.get("pack_key") != pack_key:
        lab, skipped = core.merge_start_labels(pack["labels_start"], pack)
        st.session_state.update(pack_key=pack_key, labels=lab, history={}, last_t=None, start_skipped=skipped)
    labels = st.session_state.labels

    prev = st.sidebar.file_uploader("Continuar desde un JSON de etiquetas (opcional)", type=["json"], key="prev")
    if prev is not None and st.session_state.get("prev_id") != (prev.name, prev.size):
        import json
        new, skipped = core.merge_start_labels(json.loads(prev.getvalue()), pack)
        for n, d in new.items():
            labels.setdefault(n, {}).update(d)
        st.session_state.prev_id = (prev.name, prev.size)
        st.sidebar.success(f"Cargadas {sum(len(v) for v in new.values())} etiquetas ({skipped} descartadas).")

    names = [it["name"] for it in items]
    done = {n: len(labels.get(n, {})) for n in names}
    name = st.sidebar.selectbox("Foto", names, format_func=lambda n: f"{n}  ({done[n]} etiquetados)")
    stem = next(it["stem"] for it in items if it["name"] == name)
    img, seg = pack["images"][stem], pack["segs"][stem]
    bnd, cent = _bnd_and_cent(pack_key, stem, seg.tobytes(), seg.shape)

    cur = st.sidebar.radio("Clase a asignar", classes, key="cur_class",
                           format_func=lambda c: f"{c}")
    for i, c in enumerate(classes):
        r, g, b = core.class_color(i)
        st.sidebar.markdown(f"<span style='background:rgb({r},{g},{b});padding:0 10px;margin-right:6px'>&nbsp;</span>{c}",
                            unsafe_allow_html=True)
    show_bnd = st.sidebar.checkbox("Mostrar contornos", True)
    alpha = st.sidebar.slider("Opacidad de colores", 0.0, 1.0, 0.45, 0.05)
    only = st.sidebar.selectbox("Mostrar solo clase", ["(todas)"] + classes)
    width = st.sidebar.slider("Ancho de la imagen (px)", 500, 1600, 1000, 50)
    eraser = st.sidebar.checkbox("Modo borrar (clic/rectángulo quita la etiqueta)", False)

    cols = st.sidebar.columns(2)
    hist = st.session_state.history.setdefault(name, [])
    if cols[0].button("Deshacer", disabled=not hist):
        step = hist.pop()
        for sid, old in step.items():
            if old is None:
                labels[name].pop(sid, None)
            else:
                labels[name][sid] = old
    if cols[1].button("Borrar foto", help="Quita TODAS las etiquetas de esta foto"):
        hist.append({k: v for k, v in labels.get(name, {}).items()})
        labels[name] = {}

    st.title(name)
    st.caption("Clic = un segmento · arrastrar = todos los segmentos cuyo centro cae en el rectángulo. "
               f"Clase activa: **{cur}**" + ("  (BORRAR)" if eraser else ""))
    labels.setdefault(name, {})
    view = core.render(img, seg, bnd, labels[name], classes, show_bnd, alpha, None if only == "(todas)" else only)
    h = int(view.shape[0] * width / view.shape[1])
    val = streamlit_image_coordinates(Image.fromarray(view), width=width, key=f"img_{pack_key}_{stem}",
                                      click_and_drag=True, image_format="JPEG", jpeg_quality=85, cursor="crosshair")
    if val and val.get("unix_time") != st.session_state.last_t:
        st.session_state.last_t = val.get("unix_time")
        ids = core.apply_click(val, seg, cent)
        if ids:
            step = {}
            for sid in ids:
                k = str(sid)
                step[k] = labels[name].get(k)
                if eraser:
                    labels[name].pop(k, None)
                else:
                    labels[name][k] = cur
            hist.append(step)
            st.rerun()

    total = sum(len(v) for v in labels.values())
    st.sidebar.markdown(f"**Total etiquetados:** {total}")
    counts = {c: sum(1 for v in labels.values() for x in v.values() if x == c) for c in classes}
    st.sidebar.dataframe(counts, use_container_width=True)
    stamp = time.strftime("%Y%m%d_%H%M")
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", who or "anonimo")
    st.sidebar.download_button("Descargar etiquetas (JSON)", core.labels_to_json(labels),
                               file_name=f"labels_{safe}_{stamp}.json", mime="application/json", type="primary")
    try:   # copia de seguridad local por si se cae el servidor
        Path("labeler_autosave").mkdir(exist_ok=True)
        (Path("labeler_autosave") / f"{safe}.json").write_text(core.labels_to_json(labels), encoding="utf-8")
    except OSError:
        pass


main()

"""Etiquetador web de segmentos (Streamlit). Para que otras personas generen el JSON de etiquetas.

Ejecutar:   streamlit run app/labeler_app.py
Opcional:   definir BIOCRUST_PACK=ruta\\labeling_pack.zip para que abra ese paquete solo.
Requiere:   pip install streamlit numpy pillow pyarrow<20
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
import base64
import io

import streamlit.components.v1 as components

import labeler_core as core

st.set_page_config(page_title="Etiquetador biocrust", layout="wide")

_img_click = components.declare_component("biocrust_img_click", path=str(Path(__file__).parent / "img_click"))


def clickable_image(arr, width, key):
    """Imagen clicable: clic / arrastre (izq.) y clic derecho o doble clic (borrar). Ver img_click/main.js."""
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="JPEG", quality=85)
    src = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    return _img_click(src=src, width=width, cursor="crosshair", key=key, default=None)


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
    # key fijo y opciones con texto constante: si el texto cambiara (p. ej. con el contador), Streamlit
    # lo trataría como otro widget y volvería a la primera foto.
    name = st.sidebar.selectbox("Foto", names, key="photo")
    st.sidebar.caption(f"Etiquetados en esta foto: {done[name]}")
    with st.sidebar.expander("Etiquetas por foto"):
        st.dataframe({"foto": names, "etiquetados": [done[n] for n in names]}, hide_index=True)
    stem = next(it["stem"] for it in items if it["name"] == name)
    img, seg = pack["images"][stem], pack["segs"][stem]
    bnd, cent = _bnd_and_cent(pack_key, stem, seg.tobytes(), seg.shape)

    st.sidebar.markdown("**Clases** · casilla = ver/ocultar · botón = clase activa")
    st.session_state.setdefault("cur_class", classes[0])
    for i, c in enumerate(classes):
        st.session_state.setdefault(f"vis_{c}", True)
        r, g, b = core.class_color(i)
        c1, c2, c3 = st.sidebar.columns([1, 6, 3])
        c1.markdown(f"<div style='background:rgb({r},{g},{b});width:18px;height:18px;margin-top:8px;border:1px solid #fff'></div>",
                    unsafe_allow_html=True)
        c2.checkbox(c, key=f"vis_{c}")
        if c3.button("activa" if st.session_state.cur_class == c else "usar", key=f"use_{c}",
                     type="primary" if st.session_state.cur_class == c else "secondary"):
            st.session_state.cur_class = c
            st.rerun()
    cur = st.session_state.cur_class
    def set_visible(mode):
        for c in classes:
            st.session_state[f"vis_{c}"] = (mode == "all") or (mode == "active" and c == st.session_state.cur_class)

    q = st.sidebar.columns(3)
    q[0].button("Todas", on_click=set_visible, args=("all",), help="Mostrar todas las clases")
    q[1].button("Nada", on_click=set_visible, args=("none",), help="Ocultar todas las clases")
    q[2].button("Activa", on_click=set_visible, args=("active",), help="Mostrar solo la clase activa")
    visible = {c for c in classes if st.session_state.get(f"vis_{c}", True)}
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

    st.subheader(name)
    st.caption("Clic = asigna · arrastrar = rectángulo · **clic derecho o doble clic = borrar** (también con arrastre). "
               f"Clase activa: **{cur}**" + ("  (BORRAR)" if eraser else ""))
    labels.setdefault(name, {})
    t1, t2, t3 = st.columns([1, 1, 3])
    show_bnd = t1.toggle("Contornos", True, key="show_bnd")
    show_col = t2.toggle("Colores", True, key="show_col")
    alpha = t3.slider("Opacidad", 0.05, 1.0, 0.45, 0.05, key="alpha", label_visibility="collapsed")
    if cur not in visible and show_col:
        st.warning(f"La clase activa ({cur}) está oculta: lo que asignes no se verá hasta que la muestres.")
    view = core.render(img, seg, bnd, labels[name], classes, show_bnd, alpha, visible if show_col else set())
    h = int(view.shape[0] * width / view.shape[1])
    val = clickable_image(view, width, key=f"img_{pack_key}_{stem}")
    if val and val.get("unix_time") != st.session_state.last_t:
        st.session_state.last_t = val.get("unix_time")
        ids = core.apply_click(val, seg, cent)
        erase_now = eraser or val.get("button") == 2 or val.get("double")
        if ids:
            step = {}
            for sid in ids:
                k = str(sid)
                step[k] = labels[name].get(k)
                if erase_now:
                    labels[name].pop(k, None)
                else:
                    labels[name][k] = cur
            hist.append(step)
            st.rerun()

    total = sum(len(v) for v in labels.values())
    st.sidebar.markdown(f"**Total etiquetados:** {total}")
    counts = {c: sum(1 for v in labels.values() for x in v.values() if x == c) for c in classes}
    st.sidebar.dataframe(counts)
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

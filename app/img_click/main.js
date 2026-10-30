// Imagen clicable para el etiquetador. Basado en el patrón de streamlit-image-coordinates (MIT), con botón y doble clic.
// Envía a Python: {x1,y1,x2,y2,width,height,unix_time,button,double}
//   button: 0 = izquierdo, 2 = derecho (el menú contextual del navegador se desactiva sobre la imagen)
//   double: true si fue doble clic
function send(v) { Streamlit.setComponentValue(v); }

function geom(img) { const r = img.getBoundingClientRect(); return {r, width: img.width, height: img.height}; }

function onRender(event) {
  const {src, width, cursor} = event.detail.args;
  const img = document.getElementById("image");
  if (img.src !== src) img.src = src;
  img.onload = () => {
    const w = width || img.naturalWidth;
    img.width = w;
    img.height = w * img.naturalHeight / img.naturalWidth;
    Streamlit.setFrameHeight(img.height);
  };
  if (img.complete && img.naturalWidth) img.onload();
  if (cursor) img.style.cursor = cursor;

  img.oncontextmenu = (e) => e.preventDefault();
  img.onmousedown = (down) => {
    const {r} = geom(img);
    const x1 = down.clientX - r.left, y1 = down.clientY - r.top, button = down.button;
    window.addEventListener("mouseup", (up) => {
      const g = geom(img);
      send({x1, y1, x2: up.clientX - g.r.left, y2: up.clientY - g.r.top, width: g.width, height: g.height,
            unix_time: Date.now(), button, double: false});
    }, {once: true});
  };
  img.ondblclick = (e) => {
    const g = geom(img);
    const x = e.clientX - g.r.left, y = e.clientY - g.r.top;
    send({x1: x, y1: y, x2: x, y2: y, width: g.width, height: g.height, unix_time: Date.now() + 1, button: 0, double: true});
  };
}
Streamlit.events.addEventListener(Streamlit.RENDER_EVENT, onRender);
Streamlit.setComponentReady();

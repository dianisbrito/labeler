// Imagen clicable con zoom para el etiquetador. Basado en el patrón de streamlit-image-coordinates (MIT).
// Envía a Python: {x1,y1,x2,y2,width,height,unix_time,button,double}; (x, y) son relativas a la imagen YA ampliada
// y width/height son su tamaño actual, así Python convierte bien a segmento con cualquier zoom.
//   button: 0 = izquierdo, 2 = derecho (menú contextual desactivado sobre la imagen); double: doble clic.
// Zoom: Ctrl + rueda (centrado en el cursor), botones + / − / 1:1. Mover: barras de desplazamiento o botón central arrastrando.
const MIN_ZOOM = 0.5, MAX_ZOOM = 8;
let zoom = 1, baseW = 1000, viewH = 800, lastSrc = null;

function send(v) { Streamlit.setComponentValue(v); }
function geom(img) { const r = img.getBoundingClientRect(); return {r, width: img.width, height: img.height}; }

function applyZoom(img, sc, newZoom, cx, cy) {
  // cx, cy: punto (en px de la ventana del visor) que debe quedar fijo al hacer zoom
  newZoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, newZoom));
  const oldW = img.width, oldH = img.height;
  const fx = (sc.scrollLeft + cx) / oldW, fy = (sc.scrollTop + cy) / oldH;
  zoom = newZoom;
  img.width = baseW * zoom;
  img.height = baseW * zoom * img.naturalHeight / img.naturalWidth;
  sc.scrollLeft = fx * img.width - cx;
  sc.scrollTop = fy * img.height - cy;
  document.getElementById("zlabel").textContent = Math.round(zoom * 100) + "%";
}

function onRender(event) {
  const {src, width, cursor, view_height} = event.detail.args;
  const img = document.getElementById("image"), sc = document.getElementById("scroller");
  baseW = width || baseW;
  viewH = view_height || viewH;
  sc.style.height = viewH + "px";
  Streamlit.setFrameHeight(viewH + 2);
  const size = () => {
    img.width = baseW * zoom;
    img.height = baseW * zoom * img.naturalHeight / img.naturalWidth;
  };
  if (img.src !== src) { img.src = src; }
  img.onload = size;
  if (img.complete && img.naturalWidth) size();
  if (cursor) img.style.cursor = cursor;

  const center = () => [sc.clientWidth / 2, sc.clientHeight / 2];
  document.getElementById("zin").onclick = () => applyZoom(img, sc, zoom * 1.25, ...center());
  document.getElementById("zout").onclick = () => applyZoom(img, sc, zoom / 1.25, ...center());
  document.getElementById("zreset").onclick = () => { applyZoom(img, sc, 1, 0, 0); sc.scrollLeft = 0; sc.scrollTop = 0; };
  sc.onwheel = (e) => {
    if (!(e.ctrlKey || e.metaKey)) return;          // sin Ctrl: desplazamiento normal
    e.preventDefault();
    const r = sc.getBoundingClientRect();
    applyZoom(img, sc, zoom * (e.deltaY < 0 ? 1.15 : 1 / 1.15), e.clientX - r.left, e.clientY - r.top);
  };

  img.oncontextmenu = (e) => e.preventDefault();
  img.onmousedown = (down) => {
    if (down.button === 1) {                         // botón central: mover la imagen
      down.preventDefault();
      let lx = down.clientX, ly = down.clientY;
      const move = (m) => { sc.scrollLeft -= m.clientX - lx; sc.scrollTop -= m.clientY - ly; lx = m.clientX; ly = m.clientY; };
      window.addEventListener("mousemove", move);
      window.addEventListener("mouseup", () => window.removeEventListener("mousemove", move), {once: true});
      return;
    }
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

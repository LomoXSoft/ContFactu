"""Iconos propios de ContFactu (SVG, 24×24), dibujados para recordar el color y la forma de los que el usuario
asociaba a cada función en FactuCont. No reutilizan ningún mapa de bits de Binarema."""
from markupsafe import Markup

K = 'stroke="#1b1b1b" stroke-width="1.1" stroke-linejoin="round"'

def _doc(c):  # hoja inclinada con un cuadro de color (facturas verde, albaranes azul, presupuestos amarillo, gastos granate…)
    return (f'<g transform="rotate(-14 12 12)"><path d="M6 3h9l3 3v15H6z" fill="#fff" {K}/><path d="M15 3v3h3" fill="none" {K}/>'
            f'<rect x="8.6" y="8.5" width="6.8" height="6.8" fill="{c}" {K}/></g>')

def _persona(c):
    return (f'<circle cx="12" cy="5.6" r="3" fill="{c}" {K}/><path d="M7.5 21v-6.5c0-2.6 2-4.5 4.5-4.5s4.5 1.9 4.5 4.5V21h-2.6v-5h-.6v5h-2.6v-5h-.6v5z" fill="{c}" {K}/>')

def _plus(c="#16824a"):
    return f'<path d="M9.5 3.5h5v6h6v5h-6v6h-5v-6h-6v-5h6z" fill="{c}" {K}/>'

def _dos_docs(c1, c2):
    return (f'<path d="M3 5h8l2 2v11H3z" fill="#fff" {K}/><rect x="5" y="9" width="5" height="5" fill="{c1}" {K}/>'
            f'<path d="M10 8h8l2.5 2.5V21H10z" fill="#fff" {K}/><rect x="12.5" y="12" width="5.5" height="5.5" fill="{c2}" {K}/>')

_SVG = {
    "factura": _doc("#1f9d3a"),
    "albaran": _doc("#1f4fd1"),
    "presupuesto": _doc("#f3d21a"),
    "gasto": _doc("#8e1b1b"),
    "pedido": _doc("#e2342b"),
    "mostrador": _doc("#9aa0a6"),
    "cliente": _persona("#1f9d3a"),
    "proveedor": _persona("#8e1b1b"),
    "agente": _persona("#1f4fd1"),
    "empresa": (f'<circle cx="12" cy="12" r="8.6" fill="#19b3a6" {K}/><ellipse cx="12" cy="12" rx="3.8" ry="8.6" fill="none" {K}/>'
                f'<path d="M3.6 9h16.8M3.6 15h16.8" fill="none" {K}/>'),
    "articulo": (f'<path d="M4 8l8-4 8 4v9l-8 4-8-4z" fill="#d9d9d9" {K}/><path d="M4 8l8 4 8-4M12 12v9" fill="none" {K}/>'),
    "nuevo": _plus(),
    "quitar": f'<rect x="3.5" y="9.5" width="17" height="5" rx="1" fill="#8e1b1b" {K}/>',
    "modificar": (f'<path d="M4 20l1.2-4.6L16.5 4.1l3.4 3.4L8.6 18.8z" fill="#f2c31b" {K}/><path d="M14.6 6l3.4 3.4" fill="none" {K}/>'
                  f'<path d="M4 20l1.2-4.6 3.4 3.4z" fill="#f1d7a8" {K}/><path d="M4 20l.5-1.9 1.4 1.4z" fill="#1b1b1b"/>'),
    "borrar": (f'<path d="M6 7h12l-1.2 14H7.2z" fill="#b8bcc2" {K}/><rect x="4.5" y="4.5" width="15" height="2.6" rx=".6" fill="#8d9298" {K}/>'
               f'<path d="M10 3h4v1.5h-4zM9.5 10v8M12 10v8M14.5 10v8" fill="none" {K}/>'),
    "imprimir": (f'<path d="M7 3h8l2 2v4H7z" fill="#fff" {K}/><rect x="3" y="9" width="18" height="8" rx="1.5" fill="#e9d38c" {K}/>'
                 f'<path d="M7 14h10v7H7z" fill="#fff" {K}/><circle cx="18" cy="11.6" r=".9" fill="#2a8f2a"/><path d="M9 17h6M9 19h4" fill="none" {K}/>'),
    "ver": (f'<path d="M2 12c2.6-4.2 6-6.3 10-6.3s7.4 2.1 10 6.3c-2.6 4.2-6 6.3-10 6.3S4.6 16.2 2 12z" fill="#fff" {K}/>'
            f'<circle cx="12" cy="12" r="4" fill="#c46a12" {K}/><circle cx="12" cy="12" r="1.7" fill="#1b1b1b"/>'
            f'<path d="M4 7.4l1.3 1.6M8 5l.7 1.9M12 4.3v2M16 5l-.7 1.9M20 7.4l-1.3 1.6" fill="none" stroke="#e0742a" stroke-width="1.3"/>'),
    "buscar": (f'<path d="M14 14l6.5 6.5" stroke="#1b1b1b" stroke-width="3.2" stroke-linecap="round"/>'
               f'<circle cx="9.5" cy="9.5" r="6" fill="#bfe3ff" {K}/><path d="M6.5 8a3.5 3.5 0 0 1 3-2.5" fill="none" stroke="#fff" stroke-width="1.4"/>'),
    "aceptar": f'<path d="M3 12.5l3.2-3.2 4 4L18.4 5l3 3-11.2 11.3z" fill="#1f9d3a" {K}/>',
    "deshacer": f'<circle cx="12" cy="12" r="8" fill="none" stroke="#e2342b" stroke-width="3"/><path d="M6.4 6.4l11.2 11.2" stroke="#e2342b" stroke-width="3"/>',
    "guardar": (f'<path d="M3.5 3.5h14l3 3v14h-17z" fill="#2d2d2d" {K}/><rect x="7" y="3.5" width="9" height="6" fill="#e6e6e6" {K}/>'
                f'<rect x="6" y="13" width="12" height="7.5" fill="#f4d35e" {K}/>'),
    "rectificar": _dos_docs("#1f9d3a", "#e2342b"),
    "facturar": _dos_docs("#1f4fd1", "#1f9d3a"),
    "convertir": _dos_docs("#f3d21a", "#1f9d3a"),
    "cobros": (f'<g transform="rotate(-10 12 12)"><path d="M5 3h11l3 3v15H5z" fill="#fff" {K}/>'
               f'<path d="M8 8h8M8 11h8M8 14h5" fill="none" stroke="#1f4fd1" stroke-width="1.2"/></g>'
               f'<path d="M10 17l2.5 2.5L21 11" fill="none" stroke="#e2342b" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>'),
    "recibo": (f'<rect x="2.5" y="6" width="19" height="12" rx="1.5" fill="#fff" {K}/><rect x="4.5" y="9" width="15" height="6" fill="none" stroke="#1f4fd1" stroke-width="1.1"/>'
               f'<text x="12" y="13.9" font-family="Arial" font-size="5.2" font-weight="700" fill="#1f4fd1" text-anchor="middle">ccc</text>'),
    "libros": (f'<path d="M12 6.5C9.5 4.8 6.5 4.5 2.5 5v13.5c4-.5 7 0 9.5 1.6 2.5-1.6 5.5-2.1 9.5-1.6V5c-4-.5-7-.2-9.5 1.5z" fill="#f7f1e1" {K}/>'
               f'<path d="M12 6.5v13.6M4.5 8.5c2.5-.3 4.5 0 5.8.8M4.5 11.5c2.5-.3 4.5 0 5.8.8M13.7 9.3c1.3-.8 3.3-1.1 5.8-.8M13.7 12.3c1.3-.8 3.3-1.1 5.8-.8" fill="none" {K}/>'),
    "iva": (f'<path d="M3 3l8 2.5 3.5 6-3 3-6-3.5z" fill="#1f4fd1" {K}/><path d="M3 3l5.5 5.5" stroke="#fff" stroke-width="1"/>'
            f'<rect x="8.5" y="13" width="13" height="8" fill="#1b1b1b"/><text x="15" y="19.4" font-family="Arial" font-size="6.6" font-weight="700" fill="#fff" text-anchor="middle">303</text>'),
    "listados": (f'<g transform="rotate(-12 12 12)"><path d="M5 2.5h11l3 3V21.5H5z" fill="#fff" {K}/>'
                 f'<path d="M7.5 7h9M7.5 9.6h9M7.5 12.2h9M7.5 14.8h9M7.5 17.4h6" fill="none" stroke="#1f4fd1" stroke-width="1.2"/></g>'),
    "estadisticas": (f'<rect x="2.5" y="3.5" width="19" height="17" fill="#fff" {K}/><path d="M3 20l4-7 3 3 4-8 3 5 4-3v10z" fill="#f3c31b" {K}/>'
                     f'<path d="M3 15l4-5 3 2 4-6 3 4 4-3" fill="none" stroke="#e2342b" stroke-width="1.4"/>'),
    "importar": (f'<path d="M3.5 14v6.5h17V14" fill="none" stroke="#1b1b1b" stroke-width="1.6"/>'
                 f'<path d="M9.5 3h5v7h3.5L12 16.5 6 10h3.5z" fill="#1f9d3a" {K}/>'),
    "descargar": (f'<path d="M5 2.5h10l4 4V21.5H5z" fill="#fff" {K}/><path d="M10 8h4v5h2.8L12 18l-4.8-5H10z" fill="#1f4fd1" {K}/>'),
    "excel": (f'<path d="M5 2.5h10l4 4V21.5H5z" fill="#fff" {K}/><rect x="2.5" y="8" width="10" height="9" rx="1" fill="#1d7a43" {K}/>'
              f'<path d="M5 10l5 5M10 10l-5 5" stroke="#fff" stroke-width="1.6"/>'),
    "pdf": (f'<path d="M5 2.5h10l4 4V21.5H5z" fill="#fff" {K}/><rect x="2.5" y="12" width="14" height="6.5" rx="1" fill="#c62828" {K}/>'
            f'<text x="9.5" y="17" font-family="Arial" font-size="5" font-weight="700" fill="#fff" text-anchor="middle">PDF</text>'),
    "volver": (f'<path d="M9 4L3 9.5 9 15v-3.4h5.5a3.6 3.6 0 0 1 0 7.2H11V22h3.5a6.8 6.8 0 0 0 0-13.6H9z" fill="#e2342b" {K}/>'),
    "verificar": (f'<path d="M5 2.5h10l4 4V21.5H5z" fill="#fff" {K}/><path d="M7.5 13l3 3 6-7" fill="none" stroke="#1f9d3a" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>'),
    "filtrar": f'<path d="M3 4h18l-7 8.5V20l-4-2v-5.5z" fill="#4f8fe0" {K}/>',
    "inicio": (f'<path d="M3 11.5L12 4l9 7.5" fill="none" stroke="#1b1b1b" stroke-width="1.6"/><path d="M5.5 10v10h5v-6h3v6h5V10L12 4.8z" fill="#f3d21a" {K}/>'),
    "cancelar": f'<path d="M6 4l6 6 6-6 2 2-6 6 6 6-2 2-6-6-6 6-2-2 6-6-6-6z" fill="#e2342b" {K}/>',
    "contfactu": (f'<path d="M5 2.5h10.5l3.5 3.5v15.5H5z" fill="#fff" {K}/><rect x="7.5" y="7" width="7.5" height="7.5" fill="#1f9d3a" {K}/>'
                  f'<path d="M7.5 17h9M7.5 19h6" stroke="#1f4fd1" stroke-width="1.2"/>'),
}

TIPO_ICONO = {"F": "factura", "P": "presupuesto", "A": "albaran", "G": "gasto"}

def svg(nombre, tam=20, clase="ico"):
    cuerpo = _SVG.get(nombre)
    if cuerpo is None:
        return Markup("")
    return Markup(f'<svg class="{clase}" width="{tam}" height="{tam}" viewBox="0 0 24 24" aria-hidden="true" focusable="false">{cuerpo}</svg>')

def nombres():
    return sorted(_SVG)

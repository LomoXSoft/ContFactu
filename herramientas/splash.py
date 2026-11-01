"""Genera la pantalla de carga de ContFactu (PNG cuadrado) con la versión de app/__init__.py.
Diseño propio inspirado en la disposición del de FactuCont (fondo claro azulado, nombre grande abajo a la izquierda,
banda inferior gris lavanda); no reutiliza ninguna imagen de Binarema.
Uso: python -m herramientas.splash [salida.png]   (lo llama también ContFactu.spec al construir)"""
import math, os, sys
from PIL import Image, ImageDraw, ImageFilter, ImageFont

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def version():
    ns = {}
    with open(os.path.join(RAIZ, "app", "__init__.py"), encoding="utf-8") as f:
        exec(f.read(), ns)
    return ns["__version__"]

def fuente(tam, negrita=False):
    win = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    nombres = (["segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"] if negrita else ["segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"])
    rutas = [os.path.join(win, n) for n in nombres] + [os.path.join("/usr/share/fonts/truetype/dejavu", n) for n in nombres]
    for r in rutas:
        if os.path.exists(r):
            return ImageFont.truetype(r, tam)
    return ImageFont.load_default()

def generar(salida, lado=380, ver=None):
    ver = ver or version()
    S = 2; W = lado * S                     # se dibuja al doble y se reduce (bordes suaves)
    im = Image.new("RGB", (W, W), "#eef1f7")
    d = ImageDraw.Draw(im)
    # fondo: degradado azul claro desde la esquina superior izquierda
    for y in range(W):
        for x in range(0, W, 4):
            t = min(1, math.hypot(x, y) / (W * 1.05))
            c = (int(196 + 42 * t), int(214 + 27 * t), int(236 + 11 * t))
            d.line([(x, y), (x + 3, y)], fill=c)
    # motivo propio: cuatro hojas de factura girando (verde, azul, amarillo, granate = facturas, albaranes, presupuestos, gastos)
    capa = Image.new("RGBA", (W, W), (0, 0, 0, 0)); dc = ImageDraw.Draw(capa)
    cx, cy, r = W * 0.50, W * 0.31, W * 0.125
    for i, col in enumerate([(31, 157, 58), (31, 79, 209), (243, 210, 26), (142, 27, 27)]):
        a = math.radians(90 * i - 20)
        px, py = cx + r * math.cos(a), cy + r * math.sin(a)
        hoja = Image.new("RGBA", (int(W * .15), int(W * .19)), (0, 0, 0, 0)); dh = ImageDraw.Draw(hoja)
        hw, hh = hoja.size
        dh.rounded_rectangle([2, 2, hw - 3, hh - 3], radius=10 * S, fill=(255, 255, 255, 235), outline=(60, 70, 90, 200), width=2 * S)
        dh.rectangle([hw * .25, hh * .28, hw * .75, hh * .62], fill=col + (255,), outline=(40, 40, 40, 220), width=2 * S)
        for k in range(3):
            yy = hh * (.72 + .08 * k); dh.line([(hw * .22, yy), (hw * (.78 - .12 * k), yy)], fill=(120, 140, 175, 230), width=2 * S)
        hoja = hoja.rotate(-math.degrees(a) - 90 + 25, expand=True, resample=Image.BICUBIC)
        capa.alpha_composite(hoja, (int(px - hoja.width / 2), int(py - hoja.height / 2)))
    sombra = capa.split()[3].filter(ImageFilter.GaussianBlur(6 * S)).point(lambda v: v * .35)
    im.paste((90, 100, 130), (6 * S, 8 * S), sombra)
    im.paste(capa, (0, 0), capa)
    d = ImageDraw.Draw(im)
    # banda inferior gris lavanda
    banda = int(W * .74)
    d.rectangle([0, banda, W, W], fill="#c9cde0"); d.line([(0, banda), (W, banda)], fill="#aab0cc", width=2 * S)
    f1, f2, f3, f4 = fuente(50 * S, True), fuente(40 * S, True), fuente(13 * S), fuente(12 * S, True)
    d.text((24 * S, banda - 66 * S), "ContFactu", font=f1, fill="#3a3d47")
    d.text((26 * S, banda + 10 * S), ver, font=f2, fill="#3a3d47")
    d.text((26 * S, W - 26 * S), "Cargando…", font=f3, fill="#5a6078")
    tw = d.textlength("LomoXSoft", font=f4)
    d.text((W - tw - 14 * S, W - 24 * S), "LomoXSoft", font=f4, fill="#4b3f8f")
    d.rectangle([0, 0, W - 1, W - 1], outline="#7d849e", width=2 * S)
    im = im.resize((lado, lado), Image.LANCZOS)
    os.makedirs(os.path.dirname(os.path.abspath(salida)), exist_ok=True)
    im.save(salida)
    return salida

if __name__ == "__main__":
    print(generar(sys.argv[1] if len(sys.argv) > 1 else os.path.join(RAIZ, "instalador", "splash.png")))

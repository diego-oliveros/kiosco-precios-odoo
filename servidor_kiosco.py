# =============================================================================
# KIOSCO DE PRECIOS - PROYECTO NAIROBI (Kiosko Anyeli)
# =============================================================================

import base64
import random
import threading
import xmlrpc.client
from datetime import datetime
from urllib.parse import urlparse
from flask import Flask, Response, jsonify
from waitress import serve
from kardex_credenciales import URL_ODOO, BASE_DATOS, USUARIO, CLAVE_API

app = Flask(__name__)


# --- 1. CONEXIÓN A ODOO ---
# authenticate() no entrega un token de sesión que expire por sí solo: Odoo
# vuelve a validar usuario y api key en cada execute_kw, así que autenticar
# en cada escaneo era un viaje de red completo (y una consulta más contra
# Odoo) que no aportaba nada. Se autentica una sola vez y se reutiliza el
# mismo uid mientras siga siendo válido; el candado solo entra en juego al
# (re)autenticar, nunca durante una consulta normal, para no serializar los
# escaneos de las demás terminales entre sí.
#
# Las llamadas por defecto no tienen límite de tiempo: si Odoo se queda
# pegado a mitad de una respuesta, el hilo de Waitress que la atendió se
# queda esperando para siempre. Con solo 10 hilos, unas pocas consultas así
# bastan para dejar sin servicio a las demás terminales. El transporte de
# abajo le pone un límite: pasado ese tiempo la llamada falla, cae en el
# mismo manejo de errores que ya existe, y el hilo queda libre de inmediato.
TIMEOUT_ODOO_SEGUNDOS = 8


class _TransporteConTimeout(xmlrpc.client.Transport):
    def make_connection(self, host):
        conexion = super().make_connection(host)
        conexion.timeout = TIMEOUT_ODOO_SEGUNDOS
        return conexion


class _TransporteSeguroConTimeout(xmlrpc.client.SafeTransport):
    def make_connection(self, host):
        conexion = super().make_connection(host)
        conexion.timeout = TIMEOUT_ODOO_SEGUNDOS
        return conexion


def _nuevo_transporte():
    es_https = urlparse(URL_ODOO).scheme == 'https'
    return _TransporteSeguroConTimeout() if es_https else _TransporteConTimeout()


_odoo_lock = threading.Lock()
_odoo_uid = None


def invalidar_conexion_odoo():
    global _odoo_uid
    with _odoo_lock:
        _odoo_uid = None


def get_odoo_connection():
    # Solo el uid se cachea, no el proxy de "models". Un ServerProxy guarda
    # internamente una única conexión HTTP y la reutiliza entre llamadas
    # (keep-alive); si ese mismo proxy se compartiera entre los 10 hilos de
    # Waitress, dos terminales escaneando casi al mismo tiempo terminarían
    # usando el mismo socket a la vez, con el riesgo de mezclar sus
    # respuestas. Crear el ServerProxy es solo construir el objeto en
    # memoria (no abre conexión ni viaja a Odoo hasta la primera llamada),
    # así que armarlo de nuevo en cada petición no cuesta lo que sí cuesta
    # authenticate(), que es lo único que de verdad vale la pena reutilizar.
    global _odoo_uid
    if _odoo_uid is None:
        with _odoo_lock:
            if _odoo_uid is None:  # otra terminal ya autenticó mientras esta esperaba el candado
                try:
                    common = xmlrpc.client.ServerProxy('{}/xmlrpc/2/common'.format(URL_ODOO), transport=_nuevo_transporte())
                    uid = common.authenticate(BASE_DATOS, USUARIO, CLAVE_API, {})
                    if uid:
                        _odoo_uid = uid
                except Exception as e:
                    print(f"Error de conexión a Odoo: {e}")

    if _odoo_uid is None:
        return None, None

    models = xmlrpc.client.ServerProxy('{}/xmlrpc/2/object'.format(URL_ODOO), transport=_nuevo_transporte())
    return _odoo_uid, models


# --- 2. UTILIDAD: detectar el mime real de la imagen que entrega Odoo ---
# Odoo entrega los campos binarios (image_512, image_256, etc.) ya codificados
# en base64 vía XML-RPC, pero no siempre en el mismo formato interno (puede ser
# PNG o JPEG según cómo se cargó la imagen del producto). Para que el <img>
# del navegador la muestre sin parpadeos ni íconos rotos, se detecta el
# formato real a partir de la "firma" de los primeros bytes, sin depender de
# librerías externas.
def _mime_desde_bytes(data: bytes) -> str:
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return 'image/png'
    if data[:3] == b'\xff\xd8\xff':
        return 'image/jpeg'
    if data[:6] in (b'GIF87a', b'GIF89a'):
        return 'image/gif'
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'image/webp'
    return 'image/png'  # valor por defecto razonable


def _armar_data_uri(imagen_b64):
    if not imagen_b64:
        return None
    try:
        crudos = base64.b64decode(imagen_b64)
        mime = _mime_desde_bytes(crudos)
        return f"data:{mime};base64,{imagen_b64}"
    except Exception:
        return None


# --- 3. EL FRONTEND ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
<meta name="theme-color" content="#131316">
<title>Verificador de Precios</title>
<link rel="icon" href="/static/img/favicon.ico">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700;800;900&family=Barlow:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>

  /* =====================================================================
     TOKENS DE DISEÑO
     Concepto: la pantalla es una gran "tarjeta de estante" (hang-tag) de
     ferretería, colgada sobre el muro oscuro del taller. El riel superior
     amarillo/negro evita alusión directa a cinta de peligro y franjas
     de góndola. El robot Kardex vive discreto en el pie de página.
  ===================================================================== */
  :root{
    --carbon-950:#131316;
    --carbon-850:#1d1d21;
    --carbon-750:#26262b;
    --paper:#f6f1e4;
    --paper-linea:#e3dcc9;
    --ink-950:#101014;
    --ink-700:#4a4840;
    --yellow-500:#ffc42b;
    --yellow-600:#e6ac10;
    --amber-600:#e8590c;
    --robot-navy:#1b2557;
    --robot-teal:#48e0d6;
    --vino-700:#7a1f3d;
    --vino-100:#f3d9e1;
    --amber-100:#fdecd0;

    --f-display:'Barlow Condensed', 'Arial Narrow', sans-serif;
    --f-texto:'Barlow', system-ui, -apple-system, 'Segoe UI', sans-serif;
    --f-mono:'JetBrains Mono', 'Consolas', monospace;

    /* Techo subido a propósito: esta pantalla vive en UN solo monitor de
       kiosko fijo, no es responsive genérico, así que puede ocupar mucho
       más espacio del que un sitio web normal se permitiría. */
    font-size: clamp(17px, 2.5vmin + 0.4vw, 27px);
  }

  *,*::before,*::after{ box-sizing:border-box; }

  html,body{
    height:100dvh; width:100vw;
    margin:0; padding:0;
    overflow:hidden;
    overscroll-behavior:none;
    background:var(--carbon-950);
    font-family:var(--f-texto);
    color:var(--ink-950);
    -webkit-user-select:none; user-select:none;
    -webkit-touch-callout:none;
    touch-action:manipulation;
    cursor:none;
  }

  @media (prefers-reduced-motion: reduce){
    *,*::before,*::after{
      animation-duration:.001ms !important;
      animation-iteration-count:1 !important;
      transition-duration:.001ms !important;
    }
  }

  /* Fondo del taller: viñeta radial + textura de líneas muy sutil */
  .fondo{
    position:fixed; inset:0; z-index:0; pointer-events:none;
    background:
      radial-gradient(120% 90% at 50% -8%, #232227 0%, #131316 55%, #0b0b0d 100%);
  }
  .fondo::after{
    content:"";
    position:absolute; inset:0;
    background:repeating-linear-gradient(
      115deg, rgba(255,255,255,.025) 0 2px, transparent 2px 34px
    );
    mix-blend-mode:overlay;
  }

  .kiosco{
    position:relative; z-index:1;
    height:100dvh; width:100vw;
    display:flex; flex-direction:column; align-items:center; justify-content:center;
    gap:clamp(6px, 1.2vmin, 16px);
    padding:clamp(6px, 1.2vmin, 16px);
  }

  /* ---------------------------- LA TARJETA ---------------------------- */
  .tag{
    position:relative;
    width:min(99vw, 1680px);
    height:min(98dvh, 1500px);
    max-height:99dvh;
    background:var(--paper);
    border-radius:22px;
    box-shadow:
      0 30px 60px -20px rgba(0,0,0,.65),
      0 2px 0 rgba(255,255,255,.04) inset;
    display:flex; flex-direction:column;
    overflow:hidden;
  }

  .tag__riel{
    height:clamp(8px,1.1vmin,12px);
    width:100%;
    background:repeating-linear-gradient(
      -45deg, var(--yellow-500) 0 18px, var(--ink-950) 18px 36px
    );
    flex:none;
  }

  .tag__cabecera{
    flex:none;
    padding:clamp(18px,3vmin,30px) clamp(20px,4vmin,42px) clamp(10px,1.6vmin,16px);
    display:flex; align-items:center; justify-content:space-between; gap:16px;
  }

  .tag__logo{ height:clamp(30px,4.6vmin,50px); width:auto; display:block; }

  .tag__titulo-mini{
    font-family:var(--f-display); font-weight:800;
    font-size:clamp(1.2rem, 2.6vmin, 1.8rem);
    line-height:1.05; letter-spacing:.02em;
    text-transform:uppercase; text-align:right;
    color:var(--ink-950);
    border-right:5px solid var(--yellow-500);
    padding-right:clamp(8px,1.4vmin,14px);
    white-space:nowrap;
  }

  .tag__corte{
    flex:none; border:none; margin:0 clamp(20px,4vmin,42px);
    border-top:2px dashed var(--paper-linea);
  }

  .tag__contenido{
    position:relative;
    flex:1 1 auto;
    min-height:0;
    padding:clamp(14px,2.6vmin,26px) clamp(22px,4.4vmin,46px) clamp(20px,3.6vmin,34px);
  }

  .pantalla{
    position:absolute; inset:clamp(14px,2.6vmin,26px) clamp(22px,4.4vmin,46px) clamp(20px,3.6vmin,34px);
    display:flex; flex-direction:column; align-items:center; justify-content:center;
    text-align:center; gap:clamp(8px,1.6vmin,16px);
    opacity:0; visibility:hidden;
    transform:translateY(10px) scale(.985);
    transition:opacity .45s ease, transform .45s ease, visibility 0s linear .45s;
  }
  .pantalla.activa{
    opacity:1; visibility:visible;
    transform:translateY(0) scale(1);
    transition:opacity .45s ease, transform .45s ease;
  }

  /* --------- ESTADO 1: ESPERA --------- */
  .codigo-svg{ width:clamp(140px,18vmin,230px); height:auto; opacity:.92; }
  .codigo-svg rect{ fill:var(--ink-950); }
  .codigo-svg .laser{
    fill:none; stroke:var(--amber-600); stroke-width:3.2;
    opacity:0;
    filter:drop-shadow(0 0 5px rgba(232,89,12,.85)) drop-shadow(0 0 12px rgba(232,89,12,.5));
    animation:barrido 2.6s ease-in-out infinite;
  }
  @keyframes barrido{
    0%{ transform:translateY(-2px); opacity:0; }
    12%{ opacity:.9; }
    50%{ transform:translateY(30px); opacity:.9; }
    88%{ opacity:0; }
    100%{ transform:translateY(-2px); opacity:0; }
  }

  .espera__titulo{
    font-family:var(--f-display); font-weight:800;
    font-size:clamp(2.2rem, 5.4vmin, 4.2rem);
    line-height:1.1; color:var(--ink-950);
    max-width:26ch;
  }
  .espera__sub{
    font-family:var(--f-mono);
    font-size:clamp(1rem, 2.1vmin, 1.5rem); letter-spacing:.02em;
    color:var(--ink-700);
    min-height:1.4em;
    transition:opacity .5s ease;
  }

  /* --------- ESTADO 2: ÉXITO --------- */
  .exito__imagen{
    width:clamp(220px,36vmin,460px); height:clamp(220px,36vmin,460px);
    border-radius:18px;
    background:#ffffff;
    padding:clamp(10px,1.8vmin,20px);
    display:flex; align-items:center; justify-content:center;
    overflow:hidden;
    border:1px solid var(--paper-linea);
    box-shadow:0 8px 18px -10px rgba(16,16,20,.35);
  }
  .exito__imagen img{ max-width:100%; max-height:100%; object-fit:contain; }
  .exito__imagen.sin-imagen{ display:none; }

  .exito__nombre{
    font-family:var(--f-texto); font-weight:600;
    font-size:clamp(1.7rem, 3.8vmin, 2.7rem);
    line-height:1.25; color:var(--ink-950);
    max-width:34ch;
    display:-webkit-box; -webkit-box-orient:vertical; -webkit-line-clamp:2;
    overflow:hidden;
  }

  .exito__precio-wrap{
    display:inline-block;
    background:var(--yellow-500);
    padding:clamp(6px,1.4vmin,12px) clamp(20px,4vmin,38px);
    border-radius:8px;
    box-shadow:0 4px 0 var(--yellow-600);
    animation:aparece .3s ease-out;
  }
  .exito__precio{
    font-family:var(--f-display); font-weight:900;
    font-size:clamp(3.8rem, 11.5vmin, 7.8rem);
    line-height:1; letter-spacing:-.01em;
    color:var(--ink-950);
  }
  @keyframes aparece{
    0%{ transform:translateY(8px); opacity:0; }
    100%{ transform:translateY(0); opacity:1; }
  }

  /* --------- ESTADO 3: NO ENCONTRADO ---------
     Antes usaba la paleta "vino" (roja/rosada) con un ícono de alerta tipo
     interrogación: se leía como una pantalla de error de sistema. Ahora usa
     la misma paleta ámbar/amarillo del resto de la marca, con un ícono de
     "caja en camino" en vez de una señal de alarma, para que el mensaje se
     sienta como parte normal del kiosko y no como una falla. */
  .nf__icono{
    width:clamp(70px,10vmin,100px); height:clamp(70px,10vmin,100px);
    color:var(--ink-950); opacity:.9;
  }
  .nf__titulo{
    font-family:var(--f-display); font-weight:800;
    font-size:clamp(1.9rem, 4.6vmin, 3.4rem);
    color:var(--ink-950);
    max-width:26ch; line-height:1.15;
  }
  .nf__caja{
    font-family:var(--f-texto); font-size:clamp(1.2rem, 2.7vmin, 1.7rem);
    color:var(--ink-700);
    background:var(--amber-100);
    border-left:5px solid var(--amber-600);
    border-radius:10px;
    padding:clamp(12px,2vmin,20px) clamp(16px,2.8vmin,26px);
    max-width:42ch;
  }
  .nf__caja b{ color:var(--amber-600); font-weight:700; }

  /* --------- ESTADO 4: BUSCANDO ---------
     Aparece apenas el lector envía el código, mientras se espera la
     respuesta real de Odoo — nunca se alarga artificialmente ese tiempo,
     solo se cubre el hueco silencioso que hoy existe. El texto confirma
     que el pitido del lector sí registró el código: antes, en ese mismo
     hueco, la pantalla de espera seguía igual unos segundos y varios
     clientes creían que el lector no había funcionado. El punto ámbar que
     orbita el logo reutiliza el mismo color del láser de escaneo para que
     se sienta parte de la misma familia visual y no un elemento pegado. */
  .buscando__orbit{
    position:relative;
    width:clamp(200px,34vmin,380px);
    height:clamp(200px,34vmin,380px);
  }
  .buscando__logo{
    position:absolute; inset:0;
    width:100%; height:100%;
    border-radius:50%;
    object-fit:contain;
    box-shadow:0 8px 18px -10px rgba(16,16,20,.35);
  }
  .buscando__anillo{
    position:absolute; inset:-4%;
    border-radius:50%;
    animation:orbitar 1.7s linear infinite;
  }
  .buscando__anillo::before{
    content:"";
    position:absolute;
    top:0; left:50%;
    width:clamp(14px,2.6vmin,22px); height:clamp(14px,2.6vmin,22px);
    margin-left:calc(clamp(14px,2.6vmin,22px) / -2);
    border-radius:50%;
    background:var(--amber-600);
    box-shadow:0 0 8px rgba(232,89,12,.85), 0 0 18px rgba(232,89,12,.5);
  }
  @keyframes orbitar{
    from{ transform:rotate(0deg); }
    to{ transform:rotate(360deg); }
  }

  /* ------------------------------ PIE ---------------------------------- */
  .pie{
    flex:none; z-index:1;
    display:flex; align-items:center; gap:10px;
    opacity:.8;
  }
  .pie img{
    height:clamp(26px,3.6vmin,38px); width:auto;
    filter:drop-shadow(0 0 7px rgba(72,224,214,.45)) drop-shadow(0 0 14px rgba(27,37,87,.6));
  }
  .pie span{
    font-family:var(--f-mono);
    font-size:.66rem; letter-spacing:.16em; text-transform:uppercase;
    color:var(--robot-teal);
    white-space:nowrap;
  }

  /* ------------------------------ TOAST --------------------------------- */
  .toast{
    position:fixed; left:50%; bottom:clamp(60px,9vh,110px);
    transform:translate(-50%, 12px);
    background:var(--ink-950); color:var(--paper);
    font-family:var(--f-mono); font-size:.8rem; letter-spacing:.02em;
    padding:10px 18px; border-radius:999px;
    opacity:0; pointer-events:none;
    transition:opacity .25s ease, transform .25s ease;
    z-index:20; white-space:nowrap;
  }
  .toast.visible{ opacity:1; transform:translate(-50%, 0); }

</style>
</head>
<body oncontextmenu="return false">

  <div class="fondo"></div>

  <div class="kiosco">
    <div class="tag" id="tag">
      <div class="tag__riel"></div>

      <div class="tag__cabecera">
        <img class="tag__logo" id="logo-tap" src="/static/img/logo.png" alt="Logo" draggable="false">
        <div class="tag__titulo-mini">Verificador<br>de precios</div>
      </div>
      <hr class="tag__corte">

      <div class="tag__contenido">

        <!-- ESTADO 1: ESPERA -->
        <div class="pantalla activa" id="pantalla-espera">
          <svg class="codigo-svg" viewBox="0 0 100 60" xmlns="http://www.w3.org/2000/svg">
            <rect x="4"  y="6" width="3" height="48"/><rect x="10" y="6" width="1.5" height="48"/>
            <rect x="15" y="6" width="4" height="48"/><rect x="23" y="6" width="1.5" height="48"/>
            <rect x="28" y="6" width="2" height="48"/><rect x="34" y="6" width="4" height="48"/>
            <rect x="41" y="6" width="1.5" height="48"/><rect x="46" y="6" width="3" height="48"/>
            <rect x="53" y="6" width="1.5" height="48"/><rect x="58" y="6" width="4" height="48"/>
            <rect x="66" y="6" width="2" height="48"/><rect x="71" y="6" width="1.5" height="48"/>
            <rect x="76" y="6" width="4" height="48"/><rect x="84" y="6" width="1.5" height="48"/>
            <rect x="89" y="6" width="3" height="48"/>
            <line class="laser" x1="0" y1="6" x2="100" y2="6"/>
          </svg>
          <div class="espera__titulo">¡Hola! Acerca el código de barras y descubre el precio</div>
          <div class="espera__sub" id="espera-sub">Sincronizando catálogo con bodega…</div>
        </div>

        <!-- ESTADO 4: BUSCANDO (cubre el hueco entre el pitido del lector y la respuesta de Odoo) -->
        <div class="pantalla" id="pantalla-buscando">
          <div class="buscando__orbit">
            <img class="buscando__logo" src="/static/img/espera.png" alt="Buscando" draggable="false">
            <div class="buscando__anillo"></div>
          </div>
          <div class="espera__titulo">¡Un momento, ya te traemos tu precio!</div>
          <div class="espera__sub" id="buscando-sub">Buscando tu producto…</div>
        </div>

        <!-- ESTADO 2: ÉXITO -->
        <div class="pantalla" id="pantalla-exito">
          <div class="exito__imagen sin-imagen" id="exito-imagen-caja"><img id="exito-imagen" alt=""></div>
          <div class="exito__nombre" id="exito-nombre"></div>
          <div class="exito__precio-wrap" id="exito-precio-wrap"><div class="exito__precio" id="exito-precio"></div></div>
        </div>

        <!-- ESTADO 3: NO ENCONTRADO -->
        <div class="pantalla" id="pantalla-nf">
          <svg class="nf__icono" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M3 8.2 12 4l9 4.2-9 4.2-9-4.2z" stroke-linejoin="round"/>
            <path d="M3 8.2v7.6L12 20l9-4.2V8.2" stroke-linejoin="round"/>
            <path d="M12 12.4V20"/>
            <circle cx="18.6" cy="5.2" r="3.6" fill="var(--yellow-500)" stroke="var(--ink-950)" stroke-width="1.1"/>
            <path d="M18.6 3.7v3M17.1 5.2h3" stroke="var(--ink-950)" stroke-width="1.1" stroke-linecap="round"/>
          </svg>
          <div class="nf__titulo">Aún no tenemos este código en el sistema</div>
          <div class="nf__caja">Seguimos ampliando nuestro catálogo cada semana.<br>Mientras tanto, con gusto te ayudamos en la <b id="nf-caja-num">Caja 1</b>.</div>
        </div>

      </div>
    </div>

    <div class="pie">
      <img src="/static/img/robot_kardex.png" alt="">
      <span>Powered by Proyecto Nairobi</span>
    </div>
  </div>

  <div class="toast" id="toast"></div>

  <audio id="snd-exito" src="/static/audios/success.mp3" preload="auto"></audio>
  <audio id="snd-nf" src="/static/audios/soft_error.mp3" preload="auto"></audio>

<script>
(function(){

  // ============================= CONFIGURACIÓN =============================
  const CONFIG = {
    TIEMPO_RETORNO_EXITO_MS: 6000,
    TIEMPO_RETORNO_NF_MS: 8000,
    LIMITE_INACTIVIDAD_MS: 6 * 60 * 60 * 1000,   // recarga suave tras 6h sin escaneos
    INTERVALO_CHEQUEO_INACTIVIDAD_MS: 60 * 1000,
    ROTACION_FRASES_MS: 3000,
    ROTACION_FRASES_BUSCANDO_MS: 1300, // más lento que el primer intento (900ms se sentía apurado)
    MINIMO_VISIBLE_BUSCANDO_MS: 500, // evita que la transición se vea cortada en respuestas muy rápidas
    DEBOUNCE_MISMO_CODIGO_MS: 800,
    CAJAS_DISPONIBLES: [1, 2, 3, 4, 7, 9],
    PUERTO_AGENTE_LOCAL: 55556, // debe coincidir con kiosco_agente_local.py de ESTE equipo
  };

  const FRASES_ESPERA = [
    "Acércalo al lector y no lo muevas…",
    "Seguimos ampliando nuestro catálogo cada semana…",
    "Actualizando precios en tiempo real…",
    "¿No encuentras tu producto? Con gusto te ayudamos en caja…",
    "Gracias por tu visita…",
  ];

  // "Gracias por tu paciencia" y "un segundo más" se sacaron a propósito:
  // sonaban a disculpa por una demora, y si el cliente iba a consultar un
  // segundo producto después, esa misma frase le hacía anticipar que
  // también se iba a demorar. Mejor que ninguna frase hable del tiempo que
  // toma la consulta.
  const FRASES_BUSCANDO = [
    "Ahorra comprando con nosotros…",
    "Buscando el mejor precio para ti…",
    "Aquí cuidamos tu bolsillo…",
    "Gracias por visitarnos…",
    "Calidad y buen precio, siempre…",
  ];

  // ============================== ELEMENTOS =================================
  const pantallas = {
    espera: document.getElementById('pantalla-espera'),
    buscando: document.getElementById('pantalla-buscando'),
    exito: document.getElementById('pantalla-exito'),
    nf: document.getElementById('pantalla-nf'),
  };
  const esperaSub = document.getElementById('espera-sub');
  const buscandoSub = document.getElementById('buscando-sub');
  const buscandoAnillo = document.querySelector('.buscando__anillo');
  const laserSvg = document.querySelector('.codigo-svg .laser');
  const toast = document.getElementById('toast');
  const logoTap = document.getElementById('logo-tap');
  const sndExito = document.getElementById('snd-exito');
  const sndNf = document.getElementById('snd-nf');

  let estadoActual = 'espera';
  let timerRetorno = null;
  let ultimaActividad = Date.now();
  let ultimoCodigo = '';
  let ultimoCodigoTs = 0;
  let idConsultaActual = 0; // se incrementa en cada escaneo; permite ignorar respuestas de un escaneo ya superado por otro más nuevo
  let secuenciaBuscando = FRASES_BUSCANDO;
  let posSecuenciaBuscando = 0;

  // ============================ MÁQUINA DE ESTADOS ===========================
  function mostrarEstado(nombre){
    estadoActual = nombre;
    Object.entries(pantallas).forEach(([key, el]) => {
      el.classList.toggle('activa', key === nombre);
    });
    // El navegador a veces "congela" la animación CSS del láser mientras la
    // pantalla de espera estuvo oculta (visibility:hidden) durante un
    // escaneo; forzamos su reinicio cada vez que se vuelve a mostrar, igual
    // que ya se hacía con la animación del precio.
    if(nombre === 'espera' && laserSvg) reiniciarAnimacion(laserSvg);

    if(nombre === 'buscando'){
      if(buscandoAnillo) reiniciarAnimacion(buscandoAnillo);
      secuenciaBuscando = barajarFrases(FRASES_BUSCANDO);
      posSecuenciaBuscando = 0;
      buscandoSub.textContent = secuenciaBuscando[0];
      buscandoSub.style.opacity = 1;
    }
  }

  function volverAEspera(){
    clearTimeout(timerRetorno);
    mostrarEstado('espera');
  }

  // El orden de las frases se sortea una sola vez por consulta (no en cada
  // cambio de frase): se baraja al entrar a "buscando" y esa misma secuencia
  // se repite en bucle mientras esa consulta esté en pantalla. La próxima
  // consulta vuelve a barajar, así que el orden cambia de una consulta a
  // otra pero no a la mitad de una.
  function barajarFrases(lista){
    const copia = lista.slice();
    for(let i = copia.length - 1; i > 0; i--){
      const j = Math.floor(Math.random() * (i + 1));
      [copia[i], copia[j]] = [copia[j], copia[i]];
    }
    return copia;
  }

  function reproducir(audioEl){
    try{
      audioEl.currentTime = 0;
      const p = audioEl.play();
      if(p && p.catch) p.catch(()=>{ /* política de autoplay: se reintentará con el próximo gesto real */ });
    }catch(e){ /* silencioso: el sonido nunca debe romper el flujo del kiosco */ }
  }

  function reiniciarAnimacion(el){
    el.style.animation = 'none';
    // fuerza reflow para poder relanzar el keyframe en escaneos consecutivos
    void el.offsetWidth;
    el.style.animation = '';
  }

  // =============================== BÚSQUEDA ==================================
  function buscarProducto(codigo){
    const ahora = Date.now();
    if(codigo === ultimoCodigo && (ahora - ultimoCodigoTs) < CONFIG.DEBOUNCE_MISMO_CODIGO_MS) return;
    ultimoCodigo = codigo;
    ultimoCodigoTs = ahora;
    ultimaActividad = ahora;

    clearTimeout(timerRetorno);
    mostrarEstado('buscando'); // cubre el hueco entre el pitido del lector y la respuesta real de Odoo
    const inicioBusqueda = Date.now();
    const miIdConsulta = ++idConsultaActual;

    // Solo espera lo que falte para completar el mínimo visible (si es que falta
    // algo); si Odoo ya se demoró más que eso, se muestra el resultado de inmediato.
    // Justo antes de pintar se revisa si esta sigue siendo la consulta más reciente:
    // si el cliente ya escaneó otro producto mientras esta seguía en camino, la
    // respuesta de esta (así llegue después) se descarta en silencio en vez de
    // sobrescribir lo que ya se muestra en pantalla.
    function mostrarResultado(fn){
      const faltante = CONFIG.MINIMO_VISIBLE_BUSCANDO_MS - (Date.now() - inicioBusqueda);
      function intentarPintar(){
        if(miIdConsulta !== idConsultaActual) return;
        fn();
      }
      if(faltante > 0){ setTimeout(intentarPintar, faltante); } else { intentarPintar(); }
    }

    fetch('/api/precio/' + encodeURIComponent(codigo))
      .then(r => r.json())
      .then(data => mostrarResultado(() => {
        if(data.encontrado){
          document.getElementById('exito-nombre').textContent = data.nombre;
          document.getElementById('exito-precio').textContent =
            new Intl.NumberFormat('es-CO', { style:'currency', currency:'COP', maximumFractionDigits:0 }).format(data.precio);

          const cajaImg = document.getElementById('exito-imagen-caja');
          const img = document.getElementById('exito-imagen');
          if(data.imagen){
            img.src = data.imagen;
            cajaImg.classList.remove('sin-imagen');
          }else{
            img.removeAttribute('src');
            cajaImg.classList.add('sin-imagen');
          }

          mostrarEstado('exito');
          reiniciarAnimacion(document.getElementById('exito-precio-wrap'));
          reproducir(sndExito);
          timerRetorno = setTimeout(volverAEspera, CONFIG.TIEMPO_RETORNO_EXITO_MS);
        }else{
          const opciones = CONFIG.CAJAS_DISPONIBLES;
          const caja = opciones[Math.floor(Math.random() * opciones.length)];
          document.getElementById('nf-caja-num').textContent = 'Caja ' + caja;
          mostrarEstado('nf');
          reproducir(sndNf);
          timerRetorno = setTimeout(volverAEspera, CONFIG.TIEMPO_RETORNO_NF_MS);
        }
      }))
      .catch(() => mostrarResultado(() => {
        // problema de conexión: se informa brevemente y se reintenta con recarga suave
        document.getElementById('exito-nombre').textContent = 'Problema de conexión temporal';
        document.getElementById('exito-precio').textContent = '';
        document.getElementById('exito-imagen-caja').classList.add('sin-imagen');
        mostrarEstado('exito');
        setTimeout(() => location.reload(), 3000);
      }));
  }

  // ========================== LECTOR DE CÓDIGO DE BARRAS ======================
  let bufferCodigo = '';
  let bufferTimeout;

  document.addEventListener('keydown', function(e){

    // --- No aparecen letreros ---
    if (e.key === 'F12' || e.ctrlKey || e.altKey || e.metaKey) {
        e.preventDefault();
        return;
    }
    // ----------------------------

    intentarPantallaCompleta(); // el primer evento de teclado real habilita el gesto

    if(e.key === 'Enter'){
      if(bufferCodigo.length > 0){
        buscarProducto(bufferCodigo);
        bufferCodigo = '';
      }
    }else if(e.key.length === 1){
      bufferCodigo += e.key;
    }
    clearTimeout(bufferTimeout);
    bufferTimeout = setTimeout(() => { bufferCodigo = ''; }, 1000);
  });

  // =============================== PANTALLA COMPLETA ==========================
  let gestoFullscreenUsado = false;
  function intentarPantallaCompleta(){
    if(gestoFullscreenUsado) return;
    gestoFullscreenUsado = true;
    if(!document.fullscreenElement && document.documentElement.requestFullscreen){
      document.documentElement.requestFullscreen().catch(()=>{});
    }
  }
  window.addEventListener('DOMContentLoaded', () => {
    if(document.documentElement.requestFullscreen){
      document.documentElement.requestFullscreen().catch(()=>{});
    }
    if(laserSvg) reiniciarAnimacion(laserSvg);
  });

  // Salir de pantalla completa: 5 toques en el logo, con avisos progresivos
  let toquesLogo = 0;
  let toquesTimer = null;

  function mostrarToast(texto, duracion){
    toast.textContent = texto;
    toast.classList.add('visible');
    clearTimeout(toast._t);
    toast._t = setTimeout(() => toast.classList.remove('visible'), duracion || 1800);
  }

  logoTap.addEventListener('click', function(){
    toquesLogo += 1;
    clearTimeout(toquesTimer);
    toquesTimer = setTimeout(() => { toquesLogo = 0; }, 2500);

    if(toquesLogo === 3){
      mostrarToast('2 toques más para salir del modo kiosko');
    }else if(toquesLogo === 4){
      mostrarToast('1 toque más para salir del modo kiosko');
    }else if(toquesLogo >= 5){
      toquesLogo = 0;
      mostrarToast('Cerrando modo kiosko…', 1200);
      setTimeout(() => {
        // OJO: siempre 127.0.0.1 (el agente local de ESTE equipo), nunca la IP
        // del servidor — cada terminal cierra únicamente su propio Edge.
        fetch('http://127.0.0.1:' + CONFIG.PUERTO_AGENTE_LOCAL + '/salir-kiosko', {
          method: 'POST', mode: 'no-cors'
        }).catch(() => {});
        if(document.fullscreenElement && document.exitFullscreen){
          document.exitFullscreen().catch(() => {});
        }
      }, 500);
    }
  });

  // ================================ ANTI-SUSPENSIÓN ============================
  // 1) Screen Wake Lock API: evita que Windows/Edge apaguen la pantalla.
  let wakeLock = null;
  async function pedirWakeLock(){
    try{
      if('wakeLock' in navigator){
        wakeLock = await navigator.wakeLock.request('screen');
      }
    }catch(e){ /* si el navegador o el hardware lo rechazan, el respaldo de abajo sigue activo */ }
  }
  pedirWakeLock();
  document.addEventListener('visibilitychange', () => {
    if(document.visibilityState === 'visible') pedirWakeLock();
  });

  // 2) Respaldo: recarga suave tras inactividad prolongada, solo si está en espera.
  setInterval(() => {
    if(estadoActual === 'espera' && (Date.now() - ultimaActividad) > CONFIG.LIMITE_INACTIVIDAD_MS){
      location.reload();
    }
  }, CONFIG.INTERVALO_CHEQUEO_INACTIVIDAD_MS);

  // ============================ FRASE ROTATIVA DE ESPERA =======================
  let idxFrase = 0;
  setInterval(() => {
    if(estadoActual !== 'espera') return;
    esperaSub.style.opacity = 0;
    setTimeout(() => {
      idxFrase = (idxFrase + 1) % FRASES_ESPERA.length;
      esperaSub.textContent = FRASES_ESPERA[idxFrase];
      esperaSub.style.opacity = 1;
    }, 400);
  }, CONFIG.ROTACION_FRASES_MS);

  // ========================= FRASE RÁPIDA DE BÚSQUEDA ==========================
  // Rotación más veloz que la de espera: el objetivo es transmitir actividad
  // durante una consulta que normalmente dura poco (no llenar tiempo muerto).
  setInterval(() => {
    if(estadoActual !== 'buscando') return;
    buscandoSub.style.opacity = 0;
    setTimeout(() => {
      posSecuenciaBuscando = (posSecuenciaBuscando + 1) % secuenciaBuscando.length;
      buscandoSub.textContent = secuenciaBuscando[posSecuenciaBuscando];
      buscandoSub.style.opacity = 1;
    }, 200);
  }, CONFIG.ROTACION_FRASES_BUSCANDO_MS);

})();
</script>
</body>
</html>
"""


# --- 4. RUTAS WEB ---
@app.route('/')
def index():
    # Se sirve como Response plano (no render_template_string): la plantilla no
    # usa variables de Jinja, así que se evita cualquier parseo innecesario y el
    # riesgo de que alguna llave de CSS/JS se interprete como sintaxis Jinja.
    return Response(HTML_TEMPLATE, mimetype='text/html')


@app.route('/api/precio/<codigo>')
def obtener_precio(codigo):
    hora = datetime.now().strftime('%H:%M:%S')
    uid, models = get_odoo_connection()
    if not uid:
        print(f"[{hora}] {codigo} -> SIN CONEXIÓN A ODOO")
        return jsonify({"encontrado": False})

    for intento in (1, 2):
        try:
            productos = models.execute_kw(BASE_DATOS, uid, CLAVE_API,
                'product.product', 'search_read',
                [[['barcode', '=', codigo]]],
                {'fields': ['name', 'public_price_amount', 'image_512'], 'limit': 1}
            )
            if productos:
                print(f"[{hora}] {codigo} -> OK: {productos[0].get('name')} (${productos[0].get('public_price_amount', 0.0)})")
                return jsonify({
                    "encontrado": True,
                    "nombre": productos[0].get('name', 'Sin nombre'),
                    "precio": productos[0].get('public_price_amount', 0.0),
                    "imagen": _armar_data_uri(productos[0].get('image_512')),
                })
            break
        except xmlrpc.client.Fault:
            # el uid cacheado dejó de ser válido (api key rotada, usuario dado
            # de baja, etc.): se descarta y se autentica una sola vez más
            if intento == 2:
                break
            invalidar_conexion_odoo()
            uid, models = get_odoo_connection()
            if not uid:
                print(f"[{hora}] {codigo} -> SIN CONEXIÓN A ODOO")
                return jsonify({"encontrado": False})
        except Exception:
            break

    print(f"[{hora}] {codigo} -> NO ENCONTRADO")
    return jsonify({"encontrado": False})


# --- 5. INICIO DEL SERVIDOR EN MODO PRODUCCIÓN (WAITRESS) ---
if __name__ == '__main__':
    print("=====================================================")
    print(" INICIANDO KIOSCO WEB - PROYECTO NAIROBI (PUERTO 55555)")
    print(" MODO PRODUCCIÓN: Habilitado para múltiples terminales")
    print("=====================================================")
    serve(app, host="0.0.0.0", port=55555, threads=10)

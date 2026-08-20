import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

from PIL import (
    Image,
    ImageTk,
    ImageGrab,
    ImageEnhance,
)

# Dependencias específicas por plataforma
import platform as _platform_boot
SISTEMA = _platform_boot.system()
ES_WINDOWS = SISTEMA == "Windows"
ES_MAC = SISTEMA == "Darwin"

win32gui = None
if ES_WINDOWS:
    try:
        import win32gui as _win32gui
        win32gui = _win32gui
    except ImportError:
        win32gui = None

import threading
import time
import pytesseract
import json
import os
import re
import difflib
import unicodedata
import sys
keyboard = None
if ES_WINDOWS:
    try:
        import keyboard as _keyboard
        keyboard = _keyboard
    except ImportError:
        keyboard = None
import keyring
import webbrowser
import hashlib
import platform
import uuid
import urllib.request
import urllib.error
import ctypes
import shutil
import subprocess

# Bandeja / barra de menús (opcional, pero recomendada)
try:
    import pystray
    PYSTRAY_DISPONIBLE = True
except ImportError:
    pystray = None
    PYSTRAY_DISPONIBLE = False

# Backend de shortcuts para macOS. En Windows se conserva `keyboard`.
try:
    from pynput import keyboard as pynput_keyboard
    PYNPUT_DISPONIBLE = True
except ImportError:
    pynput_keyboard = None
    PYNPUT_DISPONIBLE = False

def abrir_carpeta_sistema(ruta):
    """Abre una carpeta con el explorador nativo sin asumir Windows."""
    try:
        if ES_WINDOWS:
            os.startfile(ruta)
        elif ES_MAC:
            subprocess.Popen(["open", ruta])
        else:
            subprocess.Popen(["xdg-open", ruta])
        return True
    except Exception as e:
        print("No pude abrir la carpeta:", e)
        return False


try:
    from tkinterdnd2 import TkinterDnD, DND_FILES, DND_TEXT
    DND_DISPONIBLE = True
except ImportError:
    TkinterDnD = None
    DND_FILES = None
    DND_TEXT = None
    DND_DISPONIBLE = False

from google import genai
from google.genai import types

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


# =========================================================
# MASTERX
# =========================================================
#
# DEFAULTS:
#
# Ctrl + 1 -> Analizar zona automática
# Ctrl + 2 -> Selección manual
# Ctrl + 3 -> Configurar marco
# Ctrl + 4 -> Normal / compacto
# Ctrl + 0 -> Configurar shortcuts
# Ctrl + H -> Historial
#
# Clic izquierdo -> analizar
# Arrastrar -> mover MasterX
# Clic derecho -> selección manual
# Clic medio -> menú configuración
# Hover -> detalle respuesta
# Arrastrar imagen/texto -> analizar contenido
# ESC -> cerrar
#
# =========================================================


# =========================================================
# DIRECTORIO DEL PROGRAMA
# =========================================================

def obtener_directorio_programa():

    # Ejecutándose como EXE de PyInstaller
    if getattr(
        sys,
        "frozen",
        False
    ):

        return os.path.dirname(
            sys.executable
        )

    # Ejecutándose como .py
    return os.path.dirname(
        os.path.abspath(__file__)
    )


APP_DIR = obtener_directorio_programa()


# =========================================================
# RECURSOS EMPAQUETADOS
# =========================================================

def ruta_recurso(nombre):

    if hasattr(
        sys,
        "_MEIPASS"
    ):

        base = sys._MEIPASS

    else:

        base = APP_DIR

    return os.path.join(
        base,
        nombre
    )


# =========================================================
# CONFIGURACIÓN GENERAL
# =========================================================

TAMANO_NORMAL = 50
TAMANO_COMPACTO = 16
OPACIDAD_COMPACTO = 0.10
LICENCIA_LONGITUD = 12

# =========================================================
# LICENCIAS ONLINE
# =========================================================
#
# Cuando tengas tu Cloudflare Worker, pega aquí su endpoint:
# Ejemplo:
# LICENSE_SERVER_URL = "https://masterx-license.tucuenta.workers.dev/validate"
#
# Mientras esté vacío, MasterX usa el modo beta local:
# cualquier licencia alfanumérica de 12 caracteres funciona.
#
LICENSE_SERVER_URL = ""
LICENSE_TIMEOUT = 6

# Si el servidor no responde, una licencia que YA fue validada online
# puede seguir funcionando durante este periodo.
LICENSE_OFFLINE_GRACE_HOURS = 24

# =========================================================
# CONFIANZA IA
# =========================================================
#
# La confianza es una ESTIMACIÓN declarada por el modelo; no es
# una probabilidad calibrada. Sirve como señal práctica para decidir
# cuándo hacer una segunda comprobación.
#
CONFIANZA_FALLBACK_PRECISO = 70

# =========================================================
# ACTUALIZACIONES MASTERX
# =========================================================

MASTERX_VERSION = "0.9.2"
MASTERX_CHANNEL = "beta"

# API de GitHub: la usamos como fuente principal para evitar
# quedarnos con una copia vieja servida por raw.githubusercontent.
UPDATE_MANIFEST_API_URL = (
    "https://api.github.com/repos/"
    "Lt4Prime/MasterX-Updates/contents/version.json"
    "?ref=main"
)

# Respaldo. Si la API de GitHub falla temporalmente,
# MasterX intenta leer el RAW tradicional.
UPDATE_MANIFEST_RAW_URL = (
    "https://raw.githubusercontent.com/"
    "Lt4Prime/MasterX-Updates/main/version.json"
)

UPDATE_TIMEOUT = 6

# Último estado consultado.
estado_actualizacion = {
    "estado": "sin_comprobar",
    "version_remota": "",
    "notes": "",
    "mandatory": False,
    "download_url": "",
    "sha256": "",
    "error": "",
}

TIEMPO_RESPUESTA = 8000

modo_compacto = False

ultima_ventana = None
ultimo_titulo = ""

zona_guardada = None

ultima_respuesta_gemini = ""
ultimo_resultado_corto = ""
ultimas_opciones = []
ultima_pregunta_detectada = ""

ventana_detalle = None
ventana_shortcuts = None
ventana_api = None
ventana_licencia = None
ventana_historial = None

licencia_clave = ""
licencia_activa = False
licencia_estado = "no_configurada"
licencia_expira = ""
licencia_ultima_validacion = 0

posicion_x = 1450
posicion_y = 700


# =========================================================
# SHORTCUTS PREDETERMINADOS
# =========================================================

SHORTCUTS_DEFAULT = {
    "automatico": "ctrl+1",
    "manual": "ctrl+2",
    "marco": "ctrl+3",
    "compacto": "ctrl+4",
    "menu": "ctrl+0",
    "historial": "ctrl+h",
    "cerrar": "ctrl+9",
}

shortcuts = (
    SHORTCUTS_DEFAULT.copy()
)

hotkeys_ids = {}

# Estado de segundo plano / bandeja
tray_icon = None
tray_iniciado = False
mac_hotkeys_listener = None
masterx_en_segundo_plano = False


# =========================================================
# ESTADO DE ARRASTRE
# =========================================================

arrastre = {
    "offset_x": 0,
    "offset_y": 0,

    "inicio_x": 0,
    "inicio_y": 0,

    "movido": False,
}


# =========================================================
# RUTAS PORTABLES
# =========================================================

RUTA_CONFIG = os.path.join(
    APP_DIR,
    "masterx_config.json"
)

RUTA_DEBUG = os.path.join(
    APP_DIR,
    "masterx_procesada.png"
)

RUTA_LOGO_EXTERNO = os.path.join(
    APP_DIR,
    "masterx.png"
)

RUTA_OCR = os.path.join(
    APP_DIR,
    "OCR"
)

RUTA_TESSERACT_PORTABLE = os.path.join(
    RUTA_OCR,
    "tesseract.exe" if ES_WINDOWS else "tesseract"
)

RUTA_TESSDATA = os.path.join(
    RUTA_OCR,
    "tessdata"
)

RUTA_HISTORIAL = os.path.join(
    APP_DIR,
    "masterx_historial.json"
)

HISTORIAL_MAX = 100
historial_lock = threading.Lock()


# =========================================================
# ACTUALIZACIONES - COMPROBACIÓN
# =========================================================

def version_a_tupla(version):

    """
    Convierte versiones como 0.9.0, v0.9.1 o 1.0.0-beta
    en una tupla comparable de enteros.
    """

    numeros = re.findall(
        r"\d+",
        str(version or "")
    )

    if not numeros:
        return (0,)

    return tuple(
        int(numero)
        for numero in numeros[:4]
    )


def consultar_manifest_actualizaciones():

    """
    Consulta version.json.

    Fuente principal:
        GitHub REST API con media type RAW.

    Respaldo:
        raw.githubusercontent.com

    No descarga ni instala nada todavía.
    """

    global estado_actualizacion

    def leer_url(
        url_base,
        usar_api=False
    ):

        separador = (
            "&"
            if "?" in url_base
            else "?"
        )

        url = (
            url_base
            + separador
            + "_mx="
            + str(int(time.time() * 1000))
        )

        headers = {
            "User-Agent": (
                "MasterX/"
                + MASTERX_VERSION
                + " UpdateChecker"
            ),
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }

        if usar_api:

            # GitHub documenta este media type para obtener
            # el contenido RAW de un archivo del repositorio.
            headers[
                "Accept"
            ] = "application/vnd.github.raw+json"

            headers[
                "X-GitHub-Api-Version"
            ] = "2022-11-28"

        else:

            headers[
                "Accept"
            ] = "application/json"

        solicitud = urllib.request.Request(
            url,
            headers=headers,
            method="GET"
        )

        with urllib.request.urlopen(
            solicitud,
            timeout=UPDATE_TIMEOUT
        ) as respuesta:

            codigo_http = getattr(
                respuesta,
                "status",
                200
            )

            contenido = respuesta.read().decode(
                "utf-8",
                errors="replace"
            )

        print(
            "\n===== DEBUG UPDATE ====="
        )

        print(
            "FUENTE:",
            "GitHub API"
            if usar_api
            else "GitHub RAW"
        )

        print(
            "URL:",
            url
        )

        print(
            "HTTP:",
            codigo_http
        )

        print(
            "CONTENIDO:"
        )

        print(
            contenido
        )

        print(
            "========================\n"
        )

        return contenido

    try:

        # =================================================
        # 1. FUENTE PRINCIPAL: GITHUB API
        # =================================================

        try:

            contenido = leer_url(
                UPDATE_MANIFEST_API_URL,
                usar_api=True
            )

        except Exception as error_api:

            print(
                "GitHub API falló:",
                error_api
            )

            print(
                "Intentando GitHub RAW..."
            )

            contenido = leer_url(
                UPDATE_MANIFEST_RAW_URL,
                usar_api=False
            )

        # =================================================
        # 2. PARSEAR JSON
        # =================================================

        datos = json.loads(
            contenido
        )

        print(
            "JSON LEÍDO:",
            datos
        )

        if not isinstance(
            datos,
            dict
        ):

            raise ValueError(
                "version.json no contiene un objeto JSON."
            )

        version_remota = str(
            datos.get(
                "version",
                ""
            )
        ).strip()

        print(
            "VERSIÓN LOCAL:",
            MASTERX_VERSION
        )

        print(
            "VERSIÓN REMOTA LEÍDA:",
            version_remota
        )

        if not version_remota:

            raise ValueError(
                "version.json no contiene 'version'."
            )

        canal = str(
            datos.get(
                "channel",
                "beta"
            )
        ).strip().lower()

        resultado = {
            "estado": "actualizado",
            "version_remota": version_remota,
            "channel": canal,
            "notes": str(
                datos.get(
                    "notes",
                    ""
                )
            ).strip(),
            "mandatory": bool(
                datos.get(
                    "mandatory",
                    False
                )
            ),
            "download_url": str(
                datos.get(
                    "download_url",
                    ""
                )
            ).strip(),
            "sha256": str(
                datos.get(
                    "sha256",
                    ""
                )
            ).strip().lower(),
            "error": "",
        }

        # =================================================
        # 3. COMPARACIÓN REAL
        # =================================================

        local_tupla = version_a_tupla(
            MASTERX_VERSION
        )

        remota_tupla = version_a_tupla(
            version_remota
        )

        print(
            "COMPARACIÓN:",
            local_tupla,
            "->",
            remota_tupla
        )

        if remota_tupla > local_tupla:

            resultado[
                "estado"
            ] = "disponible"

        elif remota_tupla < local_tupla:

            # Esto puede ocurrir durante desarrollo si el .py
            # local tiene una versión superior a la publicada.
            resultado[
                "estado"
            ] = "local_superior"

        else:

            resultado[
                "estado"
            ] = "actualizado"

        estado_actualizacion = dict(
            resultado
        )

        print(
            "RESULTADO UPDATE:",
            estado_actualizacion
        )

        return dict(
            resultado
        )

    except Exception as e:

        print(
            "ERROR UPDATE:",
            repr(e)
        )

        resultado = {
            "estado": "error",
            "version_remota": "",
            "channel": "",
            "notes": "",
            "mandatory": False,
            "download_url": "",
            "sha256": "",
            "error": str(e),
        }

        estado_actualizacion = dict(
            resultado
        )

        return dict(
            resultado
        )



def texto_estado_actualizacion(
    estado=None
):

    datos = (
        estado
        if isinstance(estado, dict)
        else estado_actualizacion
    )

    estado_codigo = datos.get(
        "estado",
        "sin_comprobar"
    )

    if estado_codigo == "disponible":

        version = datos.get(
            "version_remota",
            "?"
        )

        return (
            f"● UPDATE AVAILABLE  {version}"
        )

    if estado_codigo == "actualizado":

        return (
            f"● ACTUALIZADO  {MASTERX_VERSION}"
        )

    if estado_codigo == "local_superior":

        return (
            f"● BUILD LOCAL  {MASTERX_VERSION}"
        )

    if estado_codigo == "error":

        return (
            "○ SIN CONEXIÓN / ERROR"
        )

    if estado_codigo == "comprobando":

        return (
            "◌ COMPROBANDO..."
        )

    return (
        f"○ VERSIÓN {MASTERX_VERSION}"
    )



def descargar_actualizacion(resultado, progreso_callback=None):
    """Descarga el EXE indicado por version.json y verifica su SHA-256."""
    url = str(resultado.get("download_url", "") or "").strip()
    sha_esperado = str(resultado.get("sha256", "") or "").strip().lower()
    version = str(resultado.get("version_remota", "update") or "update").strip()

    if not url:
        raise ValueError("version.json no contiene download_url.")
    if not sha_esperado:
        raise ValueError("version.json no contiene sha256.")

    nombre = f"MasterX_{version}.exe"
    destino = os.path.join(APP_DIR, nombre)
    temporal = destino + ".part"

    solicitud = urllib.request.Request(
        url,
        headers={
            "User-Agent": f"MasterX/{MASTERX_VERSION} Updater",
            "Accept": "application/octet-stream",
            "Cache-Control": "no-cache",
        },
        method="GET"
    )

    hash_archivo = hashlib.sha256()
    try:
        with urllib.request.urlopen(solicitud, timeout=30) as respuesta:
            total = int(respuesta.headers.get("Content-Length", "0") or 0)
            descargado = 0
            with open(temporal, "wb") as archivo:
                while True:
                    bloque = respuesta.read(1024 * 256)
                    if not bloque:
                        break
                    archivo.write(bloque)
                    hash_archivo.update(bloque)
                    descargado += len(bloque)
                    if progreso_callback:
                        progreso_callback(descargado, total)

        sha_real = hash_archivo.hexdigest().lower()
        if sha_real != sha_esperado:
            try:
                os.remove(temporal)
            except OSError:
                pass
            raise ValueError(
                "SHA-256 incorrecto.\n\n"
                f"Esperado: {sha_esperado}\n"
                f"Recibido: {sha_real}\n\n"
                "El archivo fue eliminado por seguridad."
            )

        os.replace(temporal, destino)
        return destino, sha_real

    except Exception:
        try:
            if os.path.exists(temporal):
                os.remove(temporal)
        except OSError:
            pass
        raise

def comprobar_actualizaciones_inicio():

    """
    Comprueba actualizaciones al iniciar.
    Si encuentra una versión nueva, ofrece descargarla y verificarla.
    """

    def tarea():

        global estado_actualizacion

        estado_actualizacion = {
            **estado_actualizacion,
            "estado": "comprobando",
        }

        resultado = consultar_manifest_actualizaciones()

        print(
            "Actualizaciones:",
            resultado.get("estado"),
            "| local:",
            MASTERX_VERSION,
            "| remota:",
            resultado.get("version_remota", "")
        )

        if resultado.get("estado") != "disponible":
            return

        def avisar():

            notas = (
                resultado.get("notes", "")
                or "Hay una nueva versión disponible."
            )

            obligatorio = (
                "\n\nEsta actualización está marcada como obligatoria."
                if resultado.get("mandatory")
                else ""
            )

            confirmar = messagebox.askyesno(
                "MasterX - Actualización",
                (
                    f"Nueva versión disponible: "
                    f"{resultado.get('version_remota')}\n"
                    f"Versión instalada: {MASTERX_VERSION}\n\n"
                    f"{notas}"
                    f"{obligatorio}\n\n"
                    "¿Quieres descargar y verificar la actualización ahora?"
                )
            )

            if not confirmar:
                return

            def descargar_en_hilo():

                try:

                    def progreso(descargado, total):

                        if total > 0:
                            porcentaje = int(
                                descargado * 100 / total
                            )

                            print(
                                f"Descargando actualización: {porcentaje}%"
                            )

                    destino, sha_real = descargar_actualizacion(
                        resultado,
                        progreso
                    )

                    def descarga_ok():

                        messagebox.showinfo(
                            "MasterX - Update",
                            (
                                "UPDATE VERIFICADO ✓\n\n"
                                f"Archivo: {os.path.basename(destino)}\n\n"
                                f"SHA-256:\n{sha_real}\n\n"
                                "La actualización fue descargada correctamente.\n\n"
                                "Esta beta todavía NO reemplaza automáticamente "
                                "el EXE actual."
                            )
                        )

                        try:
                            abrir_carpeta_sistema(
                                os.path.dirname(destino)
                            )
                        except Exception:
                            pass

                    root.after(
                        0,
                        descarga_ok
                    )

                except Exception as e:

                    def descarga_error(
                        error=str(e)
                    ):

                        messagebox.showerror(
                            "MasterX - Update",
                            (
                                "No pude descargar/verificar "
                                "la actualización.\n\n"
                                + error
                            )
                        )

                    root.after(
                        0,
                        descarga_error
                    )

            threading.Thread(
                target=descargar_en_hilo,
                daemon=True
            ).start()

        try:
            root.after(
                0,
                avisar
            )
        except Exception:
            pass

    threading.Thread(
        target=tarea,
        daemon=True
    ).start()


# =========================================================
# HISTORIAL
# =========================================================

def leer_historial():
    if not os.path.exists(RUTA_HISTORIAL):
        return []

    try:
        with open(RUTA_HISTORIAL, "r", encoding="utf-8") as archivo:
            datos = json.load(archivo)
        return datos if isinstance(datos, list) else []
    except Exception as e:
        print("Error leyendo historial:", e)
        return []


def guardar_en_historial(
    pregunta,
    opciones,
    respuesta_ia,
    fuente="Consulta"
):
    try:
        datos = interpretar_respuesta_gemini(
            respuesta_ia,
            opciones
        )
    except Exception:
        datos = {
            "tipo": "",
            "numero": "",
            "respuesta": "",
            "confianza": "",
            "explicacion": ""
        }

    registro = {
        "fecha": time.strftime("%Y-%m-%d %H:%M:%S"),
        "proveedor": nombre_proveedor_actual(),
        "fuente": fuente,
        "pregunta": pregunta,
        "opciones": list(opciones or []),
        "respuesta_raw": respuesta_ia,
        "tipo": datos.get("tipo", ""),
        "numero": datos.get("numero", ""),
        "respuesta": datos.get("respuesta", ""),
        "confianza": datos.get("confianza", ""),
        "explicacion": datos.get("explicacion", "")
    }

    try:
        with historial_lock:
            historial = leer_historial()
            historial.append(registro)
            historial = historial[-HISTORIAL_MAX:]

            with open(RUTA_HISTORIAL, "w", encoding="utf-8") as archivo:
                json.dump(
                    historial,
                    archivo,
                    indent=2,
                    ensure_ascii=False
                )
    except Exception as e:
        print("Error guardando historial:", e)


def borrar_historial():
    try:
        with historial_lock:
            with open(RUTA_HISTORIAL, "w", encoding="utf-8") as archivo:
                json.dump([], archivo)
        return True
    except Exception as e:
        print("Error borrando historial:", e)
        return False


def abrir_historial(event=None):
    global ventana_historial

    if ventana_historial is not None:
        try:
            if ventana_historial.winfo_exists():
                ventana_historial.lift()
                return
        except Exception:
            pass

    AZUL_FONDO = "#050B18"
    AZUL_PANEL = "#08182D"
    AZUL_BORDE = "#007BFF"
    AZUL_BOTON = "#0066CC"
    AZUL_HOVER = "#00A8FF"
    BLANCO = "#F4FAFF"
    GRIS = "#9CC9E8"

    ventana_historial = tk.Toplevel(root)
    ventana_historial.title("MasterX - Historial")
    ventana_historial.geometry("780x520")
    ventana_historial.minsize(720, 460)
    ventana_historial.attributes("-topmost", True)
    colorear_barra_titulo(
        ventana_historial,
        fondo="#0D0B18",
        texto="#EAF9FF",
        borde="#45D4FF"
    )
    ventana_historial.configure(bg=AZUL_BORDE)

    borde = tk.Frame(ventana_historial, bg=AZUL_BORDE)
    borde.pack(fill="both", expand=True, padx=3, pady=3)

    fondo = tk.Frame(borde, bg=AZUL_FONDO)
    fondo.pack(fill="both", expand=True)

    tk.Label(
        fondo,
        text="Historial de consultas",
        bg=AZUL_FONDO,
        fg=BLANCO,
        font=("Segoe UI", 16, "bold")
    ).pack(pady=(14, 8))

    cuerpo = tk.Frame(fondo, bg=AZUL_FONDO)
    cuerpo.pack(fill="both", expand=True, padx=14, pady=(0, 10))
    cuerpo.columnconfigure(1, weight=1)
    cuerpo.rowconfigure(0, weight=1)

    panel_lista = tk.Frame(cuerpo, bg=AZUL_PANEL)
    panel_lista.grid(row=0, column=0, sticky="ns", padx=(0, 10))

    lista = tk.Listbox(
        panel_lista,
        width=31,
        bg="#0B2340",
        fg=BLANCO,
        selectbackground=AZUL_BOTON,
        selectforeground=BLANCO,
        relief="flat",
        borderwidth=0,
        font=("Segoe UI", 9)
    )
    lista.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)

    scroll_lista = tk.Scrollbar(panel_lista, command=lista.yview)
    scroll_lista.pack(side="right", fill="y", pady=8, padx=(0, 8))
    lista.config(yscrollcommand=scroll_lista.set)

    detalle = tk.Text(
        cuerpo,
        bg=AZUL_PANEL,
        fg=BLANCO,
        insertbackground=BLANCO,
        relief="flat",
        wrap="word",
        font=("Segoe UI", 10),
        padx=12,
        pady=12
    )
    detalle.grid(row=0, column=1, sticky="nsew")
    detalle.config(state="disabled")

    registros = leer_historial()
    registros_mostrados = list(reversed(registros))

    for item in registros_mostrados:
        fecha = item.get("fecha", "")
        proveedor = item.get("proveedor", "IA")
        fuente = item.get("fuente", "Consulta")
        lista.insert("end", f"{fecha[5:16]} | {proveedor} | {fuente}")

    def texto_registro(item):
        opciones = item.get("opciones", []) or []
        opciones_txt = "\n".join(
            f"{i}. {opcion}"
            for i, opcion in enumerate(opciones, start=1)
        ) or "(sin opciones)"

        numero = item.get("numero", "")
        respuesta = item.get("respuesta", "")
        explicacion = item.get("explicacion", "")
        confianza = item.get("confianza", "")
        raw = item.get("respuesta_raw", "")

        respuesta_final = respuesta or raw or "(sin respuesta)"
        if numero:
            respuesta_final = f"Opción {numero}: {respuesta_final}"

        return (
            f"Fecha: {item.get('fecha', '')}\n"
            f"Proveedor: {item.get('proveedor', '')}\n"
            f"Fuente: {item.get('fuente', '')}\n\n"
            f"PREGUNTA\n{item.get('pregunta', '')}\n\n"
            f"OPCIONES\n{opciones_txt}\n\n"
            f"RESPUESTA\n{respuesta_final}\n\n"
            f"CONFIANZA IA\n{(str(confianza) + '%') if confianza else '(no informada)'}\n\n"
            f"EXPLICACIÓN\n{explicacion or '(sin explicación)'}"
        )

    def mostrar_seleccion(event=None):
        seleccion = lista.curselection()
        if not seleccion:
            return

        item = registros_mostrados[seleccion[0]]
        detalle.config(state="normal")
        detalle.delete("1.0", "end")
        detalle.insert("1.0", texto_registro(item))
        detalle.config(state="disabled")

    lista.bind("<<ListboxSelect>>", mostrar_seleccion)

    def copiar_respuesta():
        seleccion = lista.curselection()
        if not seleccion:
            return
        item = registros_mostrados[seleccion[0]]
        texto = item.get("respuesta", "") or item.get("respuesta_raw", "")
        if item.get("numero"):
            texto = f"{item.get('numero')}. {texto}"
        root.clipboard_clear()
        root.clipboard_append(texto)

    def borrar_todo():
        if not messagebox.askyesno(
            "MasterX",
            "¿Borrar todo el historial?",
            parent=ventana_historial
        ):
            return

        if borrar_historial():
            lista.delete(0, "end")
            registros_mostrados.clear()
            detalle.config(state="normal")
            detalle.delete("1.0", "end")
            detalle.config(state="disabled")

    def boton_azul(padre, texto, comando):
        b = tk.Button(
            padre,
            text=texto,
            command=comando,
            bg=AZUL_BOTON,
            fg=BLANCO,
            activebackground=AZUL_HOVER,
            activeforeground=BLANCO,
            relief="flat",
            borderwidth=0,
            cursor="hand2",
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=5
        )
        b.bind("<Enter>", lambda e: b.config(bg=AZUL_HOVER))
        b.bind("<Leave>", lambda e: b.config(bg=AZUL_BOTON))
        return b

    barra = tk.Frame(fondo, bg=AZUL_FONDO)
    barra.pack(fill="x", padx=14, pady=(0, 12))

    boton_azul(barra, "Borrar historial", borrar_todo).pack(side="left")
    boton_azul(barra, "Copiar respuesta", copiar_respuesta).pack(side="right")
    boton_azul(barra, "Cerrar", ventana_historial.destroy).pack(side="right", padx=8)

    if registros_mostrados:
        lista.selection_set(0)
        mostrar_seleccion()


# =========================================================
# TEXTO / IMÁGENES ARRASTRADOS
# =========================================================

def procesar_texto_directo(texto, fuente="Texto arrastrado"):
    texto = str(texto or "").strip()

    if not texto:
        root.after(0, lambda: mostrar_mensaje_temporal("?"))
        return

    if not licencia_activa:
        root.after(
            0,
            lambda: abrir_configuracion_licencia(obligatoria=False)
        )
        return

    if not proveedor_configurado():
        root.after(
            0,
            lambda: abrir_configuracion_proveedor_actual(obligatoria=False)
        )
        return

    root.after(
        0,
        lambda: boton.config(
            image="",
            text="...",
            font=("Segoe UI", 10 if modo_compacto else 14, "bold")
        )
    )

    pregunta, opciones = estructurar_pregunta(
        texto,
        modo="manual"
    )

    # Si el parser no pudo separar bien un texto libre, se manda completo.
    if pregunta.startswith("No pude identificar"):
        pregunta = texto
        opciones = []

    if opciones == ["No pude identificar opciones."]:
        opciones = []

    respuesta = consultar_ia(
        pregunta,
        opciones
    )

    guardar_en_historial(
        pregunta,
        opciones,
        respuesta,
        fuente=fuente
    )

    root.after(
        0,
        lambda: mostrar_resultado_compacto(
            respuesta,
            opciones,
            pregunta
        )
    )


def procesar_imagen_arrastrada(ruta):
    try:
        with Image.open(ruta) as img:
            imagen = img.convert("RGB").copy()

        procesar_imagen_manual(
            imagen,
            f"Arrastre: {os.path.basename(ruta)}",
            fuente="Imagen arrastrada"
        )

    except Exception as e:
        print("Error procesando imagen arrastrada:", e)
        root.after(0, lambda: mostrar_mensaje_temporal("!"))


def procesar_archivo_texto_arrastrado(ruta):
    try:
        with open(ruta, "r", encoding="utf-8", errors="replace") as archivo:
            texto = archivo.read()

        procesar_texto_directo(
            texto,
            fuente=f"Archivo: {os.path.basename(ruta)}"
        )
    except Exception as e:
        print("Error leyendo texto arrastrado:", e)
        root.after(0, lambda: mostrar_mensaje_temporal("!"))


def manejar_drop(event):
    data = str(getattr(event, "data", "") or "").strip()
    if not data:
        return

    try:
        elementos = list(root.tk.splitlist(data))
    except Exception:
        elementos = [data]

    rutas = [x for x in elementos if os.path.exists(x)]

    if rutas:
        ruta = rutas[0]
        extension = os.path.splitext(ruta)[1].lower()

        imagenes = {
            ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"
        }
        textos = {
            ".txt", ".md", ".csv", ".json", ".log"
        }

        if extension in imagenes:
            threading.Thread(
                target=procesar_imagen_arrastrada,
                args=(ruta,),
                daemon=True
            ).start()
            return

        if extension in textos:
            threading.Thread(
                target=procesar_archivo_texto_arrastrado,
                args=(ruta,),
                daemon=True
            ).start()
            return

        root.after(0, lambda: mostrar_mensaje_temporal("?"))
        return

    # Si no es archivo, lo tratamos como texto arrastrado.
    threading.Thread(
        target=procesar_texto_directo,
        args=(data, "Texto arrastrado"),
        daemon=True
    ).start()


# =========================================================
# TESSERACT PORTABLE
# =========================================================

def configurar_tesseract():
    """Localiza Tesseract en el bundle portable o en una instalación del sistema."""

    candidatos = []

    # 1) OCR incluido junto a MasterX.
    candidatos.append(RUTA_TESSERACT_PORTABLE)

    # 2) Ejecutable disponible en PATH.
    ruta_path = shutil.which("tesseract")
    if ruta_path:
        candidatos.append(ruta_path)

    # 3) Rutas habituales por sistema.
    if ES_WINDOWS:
        candidatos.extend([
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        ])
    elif ES_MAC:
        candidatos.extend([
            "/opt/homebrew/bin/tesseract",   # Apple Silicon + Homebrew
            "/usr/local/bin/tesseract",     # Intel + Homebrew
            "/opt/local/bin/tesseract",     # MacPorts
        ])

    for ruta in candidatos:
        if ruta and os.path.isfile(ruta):
            pytesseract.pytesseract.tesseract_cmd = ruta

            # Solo fijamos TESSDATA_PREFIX cuando realmente empaquetamos tessdata.
            if os.path.isdir(RUTA_TESSDATA):
                os.environ["TESSDATA_PREFIX"] = RUTA_TESSDATA

            print("Tesseract configurado:", ruta)
            return True

    print("ERROR: No encontré Tesseract.")
    if ES_MAC:
        print("macOS: instala Tesseract o inclúyelo en la carpeta OCR del bundle.")
    return False


# Inicialización real del OCR. Antes la función existía, pero su resultado
# nunca se asignaba y TESSERACT_OK quedaba indefinido.
TESSERACT_OK = configurar_tesseract()


# =========================================================
# PROVEEDORES DE IA
# =========================================================

GEMINI_MODEL_RAPIDO = "gemini-3.5-flash-lite"
GEMINI_MODEL_PRECISO = "gemini-3.6-flash"
GEMINI_MODO = "rapido"  # "rapido" o "preciso"
OPENAI_MODEL = "gpt-5.6"

def obtener_modelo_gemini():
    return (
        GEMINI_MODEL_PRECISO
        if GEMINI_MODO == "preciso"
        else GEMINI_MODEL_RAPIDO
    )

KEYRING_SERVICIO = "MasterX"
KEYRING_USUARIO = "GeminiAPI"
KEYRING_USUARIO_OPENAI = "OpenAIAPI"

# Proveedor seleccionado: "gemini" u "openai".
PROVEEDOR_IA = "gemini"

gemini_api_key = None
gemini_client = None

openai_api_key = None
openai_client = None
ventana_openai = None


# =========================================================
# OBTENER API KEY
# =========================================================

def obtener_api_key():

    # =====================================================
    # 1. KEYRING / CREDENTIAL MANAGER
    # =====================================================

    try:

        clave = keyring.get_password(
            KEYRING_SERVICIO,
            KEYRING_USUARIO
        )

        if clave:

            clave = clave.strip()

            if clave:

                print(
                    "API Gemini: cargada desde almacén seguro."
                )

                return clave

    except Exception as e:

        print(
            "No pude leer keyring:",
            e
        )

    # =====================================================
    # 2. VARIABLE DE ENTORNO
    #
    # Esto mantiene compatibilidad con tu PC actual.
    # =====================================================

    clave_entorno = os.getenv(
        "GEMINI_API_KEY"
    )

    if clave_entorno:

        clave_entorno = (
            clave_entorno.strip()
        )

        if clave_entorno:

            print(
                "API Gemini: cargada desde variable de entorno."
            )

            return clave_entorno

    return None


# =========================================================
# GUARDAR API KEY
# =========================================================

def guardar_api_key(
    clave
):

    clave = clave.strip()

    if not clave:

        return False

    try:

        keyring.set_password(
            KEYRING_SERVICIO,
            KEYRING_USUARIO,
            clave
        )

        print(
            "API key guardada en keyring."
        )

        return True

    except Exception as e:

        print(
            "No pude guardar API key:",
            e
        )

        return False


# =========================================================
# ELIMINAR API KEY
# =========================================================

def eliminar_api_key():

    try:

        keyring.delete_password(
            KEYRING_SERVICIO,
            KEYRING_USUARIO
        )

        print(
            "API key eliminada."
        )

        return True

    except Exception as e:

        print(
            "No pude eliminar la API key:",
            e
        )

        return False


# =========================================================
# INICIALIZAR GEMINI
# =========================================================

def inicializar_gemini():

    global gemini_api_key
    global gemini_client

    gemini_api_key = (
        obtener_api_key()
    )

    if not gemini_api_key:

        gemini_client = None

        print(
            "Gemini: sin API key."
        )

        return False

    try:

        gemini_client = genai.Client(
            api_key=gemini_api_key
        )

        print(
            "Gemini inicializado."
        )

        return True

    except Exception as e:

        print(
            "Error inicializando Gemini:",
            e
        )

        gemini_client = None

        return False


# =========================================================
# PROBAR API KEY
# =========================================================

def probar_api_key(
    clave
):

    clave = clave.strip()

    if not clave:

        return (
            False,
            "La API key está vacía."
        )

    try:

        cliente_prueba = genai.Client(
            api_key=clave
        )

        respuesta = (
            cliente_prueba
            .models
            .generate_content(
                model=obtener_modelo_gemini(),

                contents=(
                    "Responde únicamente con la palabra OK."
                ),

                config=types.GenerateContentConfig(
                    max_output_tokens=10
                )
            )
        )

        if not respuesta.text:

            return (
                False,
                "Gemini no devolvió texto."
            )

        texto = (
            respuesta.text
            .strip()
        )

        print(
            "Prueba Gemini:",
            texto
        )

        return (
            True,
            texto
        )

    except Exception as e:

        return (
            False,
            str(e)
        )


# =========================================================
# ESTADO GEMINI
# =========================================================

def texto_estado_gemini():

    if gemini_client is None:

        return (
            "Gemini: No configurado"
        )

    return (
        "Gemini: Conectado"
    )


# =========================================================
# OPENAI
# =========================================================

def obtener_api_key_openai():

    try:
        clave = keyring.get_password(
            KEYRING_SERVICIO,
            KEYRING_USUARIO_OPENAI
        )
        if clave and clave.strip():
            print("API OpenAI: cargada desde almacén seguro.")
            return clave.strip()
    except Exception as e:
        print("No pude leer OpenAI desde keyring:", e)

    clave_entorno = os.getenv("OPENAI_API_KEY")
    if clave_entorno and clave_entorno.strip():
        print("API OpenAI: cargada desde variable de entorno.")
        return clave_entorno.strip()

    return None


def guardar_api_key_openai(clave):

    clave = clave.strip()
    if not clave:
        return False

    try:
        keyring.set_password(
            KEYRING_SERVICIO,
            KEYRING_USUARIO_OPENAI,
            clave
        )
        print("API OpenAI guardada en keyring.")
        return True
    except Exception as e:
        print("No pude guardar API OpenAI:", e)
        return False


def inicializar_openai():

    global openai_api_key
    global openai_client

    if OpenAI is None:
        openai_client = None
        print("OpenAI SDK no está instalado.")
        return False

    openai_api_key = obtener_api_key_openai()

    if not openai_api_key:
        openai_client = None
        print("OpenAI: sin API key.")
        return False

    try:
        openai_client = OpenAI(api_key=openai_api_key)
        print("OpenAI inicializado.")
        return True
    except Exception as e:
        print("Error inicializando OpenAI:", e)
        openai_client = None
        return False


def interpretar_error_openai(error):
    """Convierte errores técnicos de OpenAI en mensajes útiles para el usuario."""

    texto = str(error)
    texto_lower = texto.lower()

    if (
        "insufficient_quota" in texto_lower
        or "exceeded your current quota" in texto_lower
        or "error code: 429" in texto_lower
    ):
        return (
            "SIN_CUOTA",
            "La API key fue aceptada, pero la cuenta/proyecto de OpenAI "
            "no tiene cuota o crédito disponible.\n\n"
            "Puedes revisar Billing/Credits en OpenAI o usar Gemini en MasterX."
        )

    if (
        "invalid_api_key" in texto_lower
        or "incorrect api key" in texto_lower
        or "error code: 401" in texto_lower
    ):
        return (
            "API_INVALIDA",
            "La API key de OpenAI no es válida o fue revocada. "
            "Crea una nueva clave e inténtalo otra vez."
        )

    if "rate_limit" in texto_lower or "rate limit" in texto_lower:
        return (
            "LIMITE",
            "OpenAI está limitando temporalmente las solicitudes. "
            "Espera un momento e inténtalo de nuevo."
        )

    if (
        "connection" in texto_lower
        or "timeout" in texto_lower
        or "timed out" in texto_lower
    ):
        return (
            "CONEXION",
            "No pude conectar con OpenAI. Revisa tu conexión a Internet "
            "e inténtalo otra vez."
        )

    return (
        "OTRO",
        "OpenAI devolvió un error:\n\n" + texto
    )


def probar_api_key_openai(clave):

    if OpenAI is None:
        return (
            False,
            "SDK_NO_INSTALADO|Falta instalar el paquete openai. "
            "Ejecuta: py -m pip install openai"
        )

    clave = clave.strip()
    if not clave:
        return False, "API_INVALIDA|La API key está vacía."

    try:
        cliente = OpenAI(api_key=clave)
        respuesta = cliente.responses.create(
            model=OPENAI_MODEL,
            input="Responde únicamente con la palabra OK.",
            max_output_tokens=20
        )
        texto = (respuesta.output_text or "").strip()
        if not texto:
            return False, "OTRO|OpenAI no devolvió texto."
        print("Prueba OpenAI:", texto)
        return True, texto
    except Exception as e:
        codigo, mensaje = interpretar_error_openai(e)
        return False, codigo + "|" + mensaje


def texto_estado_openai():
    if OpenAI is None:
        return "OpenAI: SDK no instalado"
    if openai_client is None:
        return "OpenAI: No configurado"
    return "OpenAI: Conectado"


def proveedor_configurado():
    if PROVEEDOR_IA == "openai":
        return openai_client is not None
    return gemini_client is not None


def nombre_proveedor_actual():
    return "OpenAI" if PROVEEDOR_IA == "openai" else "Gemini"


def abrir_configuracion_proveedor_actual(obligatoria=False):
    if PROVEEDOR_IA == "openai":
        abrir_configuracion_openai(obligatoria=obligatoria)
    else:
        abrir_configuracion_api(obligatoria=obligatoria)


# =========================================================
# CONFIGURACIÓN LOCAL
# =========================================================

def cargar_configuracion():

    global zona_guardada
    global posicion_x
    global posicion_y
    global shortcuts
    global OPACIDAD_COMPACTO
    global licencia_clave
    global licencia_activa
    global licencia_estado
    global licencia_expira
    global licencia_ultima_validacion
    global PROVEEDOR_IA
    global GEMINI_MODO

    if not os.path.exists(
        RUTA_CONFIG
    ):

        zona_guardada = None
        shortcuts = SHORTCUTS_DEFAULT.copy()
        licencia_clave = ""
        licencia_activa = False
        PROVEEDOR_IA = "gemini"
        GEMINI_MODO = "rapido"
        return

    try:

        with open(
            RUTA_CONFIG,
            "r",
            encoding="utf-8"
        ) as archivo:

            datos = json.load(archivo)

        zona_guardada = datos.get(
            "zona_automatica"
        )

        posicion = datos.get(
            "posicion",
            {}
        )

        posicion_x = posicion.get(
            "x",
            posicion_x
        )

        posicion_y = posicion.get(
            "y",
            posicion_y
        )

        shortcuts_guardados = datos.get(
            "shortcuts",
            {}
        )

        shortcuts = SHORTCUTS_DEFAULT.copy()
        shortcuts.update(shortcuts_guardados)

        proveedor_guardado = str(
            datos.get("proveedor_ia", "gemini")
        ).strip().lower()
        PROVEEDOR_IA = (
            proveedor_guardado
            if proveedor_guardado in ("gemini", "openai")
            else "gemini"
        )

        modo_gemini_guardado = str(
            datos.get("gemini_modo", "rapido")
        ).strip().lower()
        GEMINI_MODO = (
            modo_gemini_guardado
            if modo_gemini_guardado in ("rapido", "preciso")
            else "rapido"
        )

        # Opacidad compacta guardada entre 10% y 100%.
        try:
            opacidad = float(
                datos.get(
                    "opacidad_compacto",
                    OPACIDAD_COMPACTO
                )
            )
            OPACIDAD_COMPACTO = max(
                0.10,
                min(1.0, opacidad)
            )
        except Exception:
            OPACIDAD_COMPACTO = 0.10

        # Licencia temporal local.
        licencia_clave = normalizar_licencia(
            datos.get(
                "licencia",
                ""
            )
        )
        licencia_activa = validar_licencia(
            licencia_clave
        )

        licencia_estado = str(
            datos.get("licencia_estado", "local" if licencia_activa else "no_configurada")
        )

        licencia_expira = str(
            datos.get("licencia_expira", "")
        )

        try:
            licencia_ultima_validacion = float(
                datos.get("licencia_ultima_validacion", 0) or 0
            )
        except Exception:
            licencia_ultima_validacion = 0

        print(
            "Zona cargada:",
            zona_guardada
        )

        print(
            "Posición:",
            posicion_x,
            posicion_y
        )

        print(
            "Shortcuts:",
            shortcuts
        )

        print(
            "Licencia:",
            "activa" if licencia_activa else "no configurada"
        )

        print(
            "Opacidad compacta:",
            OPACIDAD_COMPACTO
        )

        print(
            "Proveedor IA:",
            PROVEEDOR_IA
        )

    except Exception as e:

        print(
            "Error cargando configuración:",
            e
        )

        shortcuts = SHORTCUTS_DEFAULT.copy()
        licencia_clave = ""
        licencia_activa = False

# =========================================================
# GUARDAR ESTADO
# =========================================================

def guardar_estado():

    datos = {

        "zona_automatica":
            zona_guardada,

        "posicion": {
            "x": posicion_x,
            "y": posicion_y,
        },

        "shortcuts": shortcuts,

        "proveedor_ia": PROVEEDOR_IA,

        "gemini_modo": GEMINI_MODO,

        "opacidad_compacto":
            OPACIDAD_COMPACTO,

        # Temporal: la licencia se guarda en la configuración local.
        # Más adelante puede sustituirse por validación remota.
        "licencia":
            licencia_clave,

        "licencia_estado":
            licencia_estado,

        "licencia_expira":
            licencia_expira,

        "licencia_ultima_validacion":
            licencia_ultima_validacion,
    }

    try:

        with open(
            RUTA_CONFIG,
            "w",
            encoding="utf-8"
        ) as archivo:

            json.dump(
                datos,
                archivo,
                indent=4,
                ensure_ascii=False
            )

    except Exception as e:

        print(
            "Error guardando configuración:",
            e
        )

# =========================================================
# GUARDAR ZONA
# =========================================================

def guardar_configuracion(
    zona
):

    global zona_guardada

    zona_guardada = zona

    guardar_estado()

    print(
        "Zona guardada:",
        zona
    )


# =========================================================
# VIGILAR VENTANA ACTIVA
# =========================================================

def vigilar_ventana():
    """Recuerda la ventana activa. Implementación completa en Windows; fallback seguro en macOS."""
    global ultima_ventana
    global ultimo_titulo

    while True:
        try:
            if ES_WINDOWS and win32gui is not None:
                hwnd = win32gui.GetForegroundWindow()
                if hwnd:
                    titulo = win32gui.GetWindowText(hwnd)
                    if titulo and "MasterX" not in titulo:
                        ultima_ventana = hwnd
                        ultimo_titulo = titulo
            elif ES_MAC:
                # En macOS la captura de pantalla sigue disponible, pero obtener el
                # rectángulo exacto de otra app requiere Quartz/Accesibilidad.
                # Se deja un fallback seguro hasta que ese permiso esté disponible.
                ultima_ventana = None
        except Exception:
            pass

        time.sleep(0.1)


# =========================================================
# RECTÁNGULO VENTANA
# =========================================================

def obtener_rectangulo_ventana(hwnd):
    if not ES_WINDOWS or win32gui is None or hwnd is None:
        return None

    try:
        izquierda, arriba, derecha, abajo = win32gui.GetWindowRect(hwnd)
        if derecha <= izquierda or abajo <= arriba:
            return None
        return izquierda, arriba, derecha, abajo
    except Exception:
        return None


# =========================================================
# CAPTURA
# =========================================================

def capturar_ventana(
    hwnd
):

    rect = (
        obtener_rectangulo_ventana(
            hwnd
        )
    )

    if rect is None:

        return None

    try:

        return ImageGrab.grab(
            bbox=rect,
            all_screens=True
        )

    except Exception as e:

        print(
            "Error capturando:",
            e
        )

        return None


# =========================================================
# PREPROCESAMIENTO
# =========================================================

def preparar_imagen(
    imagen,
    escala=2.5,
    contraste=2.0
):

    imagen = imagen.resize(
        (
            int(
                imagen.width
                * escala
            ),

            int(
                imagen.height
                * escala
            )
        ),

        Image.Resampling.LANCZOS
    )

    imagen = imagen.convert(
        "L"
    )

    imagen = (
        ImageEnhance.Contrast(
            imagen
        )
        .enhance(
            contraste
        )
    )

    return imagen


# =========================================================
# OCR PASADA 1
# =========================================================

def hacer_ocr(
    imagen
):

    if not TESSERACT_OK:

        return (
            "ERROR OCR: "
            "Tesseract no encontrado."
        )

    try:

        procesada = preparar_imagen(
            imagen,
            escala=2.5,
            contraste=2.0
        )

        try:

            procesada.save(
                RUTA_DEBUG
            )

        except Exception:

            pass

        texto = (
            pytesseract.image_to_string(
                procesada,
                lang="spa",
                config="--oem 3 --psm 6"
            )
        )

        texto = texto.strip()

        if not texto:

            return (
                "No pude detectar texto."
            )

        print(
            "\n===== OCR PASADA 1 ====="
        )

        print(
            texto
        )

        print(
            "========================\n"
        )

        return texto

    except Exception as e:

        return (
            "ERROR OCR:\n"
            + str(e)
        )


# =========================================================
# OCR PASADA 2
# =========================================================

def hacer_ocr_segunda_pasada(
    imagen
):

    try:

        procesada = preparar_imagen(
            imagen,
            escala=3.0,
            contraste=2.4
        )

        texto = (
            pytesseract.image_to_string(
                procesada,
                lang="spa",
                config="--oem 3 --psm 4"
            )
        )

        texto = texto.strip()

        print(
            "\n===== OCR PASADA 2 ====="
        )

        print(
            texto
        )

        print(
            "========================\n"
        )

        return texto

    except Exception as e:

        print(
            "Error OCR 2:",
            e
        )

        return ""


# =========================================================
# LIMPIAR LÍNEAS
# =========================================================

def limpiar_lineas(
    texto
):

    resultado = []

    for linea in (
        texto.splitlines()
    ):

        linea = linea.strip()

        if linea:

            resultado.append(
                linea
            )

    return resultado


# =========================================================
# RUIDO AUTOMÁTICO
# =========================================================

def es_ruido_basico(
    linea
):

    l = (
        linea.lower()
        .strip()
    )

    ruido = {

        "lecciones",
        "noticias",
        "calendario",
        "tareas",
        "estudiantes",
        "profesores",
        "portafolio",
        "búsqueda",
        "busqueda",
        "estado",
        "preguntas",
        "continuar",
        "previo",
        "anterior",
        "siguiente",
        "instrucciones",
        "contacto",
        "panel de control",
        "recursos",
    }

    limpio = (
        l.replace(",", "")
        .replace(".", "")
        .replace("(", "")
        .replace(")", "")
        .replace("[", "")
        .replace("]", "")
        .replace(":", "")
        .strip()
    )

    if limpio in ruido:

        return True

    basura_parcial = [

        "campusvirtual",
        "student_take_quiz",
        "assignment/display",
        "assignment/start",
        "http://",
        "https://",
        "tiempo restante",
        "fecha límite",
        "fecha limite",
    ]

    return any(
        fragmento in l

        for fragmento
        in basura_parcial
    )


# =========================================================
# NORMALIZACIÓN OCR MÉDICA CONSERVADORA
# =========================================================

def normalizar_para_comparar(texto):

    texto = str(texto or "").lower().strip()

    # Quitar acentos solo para comparar, no para mostrar.
    texto = "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )

    texto = re.sub(
        r"[^a-z0-9]+",
        " ",
        texto
    )

    return re.sub(
        r"\s+",
        " ",
        texto
    ).strip()


def corregir_errores_ocr_medicos(texto):

    """
    Corrige únicamente confusiones OCR de formato muy probables.
    No intenta 'resolver' ni completar conocimiento médico.
    """

    if not texto:
        return texto

    original = str(texto)
    t = original

    # 1L / lL / iL delante de números suele ser IL en nomenclatura
    # de interleucinas. Solo se toca cuando hay guion + número.
    t = re.sub(
        r"\b(?:1L|lL|iL)-(?=\d)",
        "IL-",
        t,
        flags=re.IGNORECASE
    )

    # Espacios OCR dentro de IL-6 / TNF-alfa.
    t = re.sub(
        r"\bIL\s*-\s*(\d+)",
        r"IL-\1",
        t,
        flags=re.IGNORECASE
    )

    t = re.sub(
        r"\bTNF\s*-\s*",
        "TNF-",
        t,
        flags=re.IGNORECASE
    )

    # Formas pegadas muy comunes por OCR.
    t = re.sub(
        r"\bTNF\s*alfa\b",
        "TNF-alfa",
        t,
        flags=re.IGNORECASE
    )

    t = re.sub(
        r"\bTNF\s*beta\b",
        "TNF-beta",
        t,
        flags=re.IGNORECASE
    )

    # "interleucina - 1" -> "interleucina-1"
    t = re.sub(
        r"\b(interleucina)\s*-\s*(\d+)",
        r"\1-\2",
        t,
        flags=re.IGNORECASE
    )

    # Limpiar espacios repetidos / antes de signos.
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\s+([,.;:])", r"\1", t)

    return t.strip()


# =========================================================
# INSTRUCCIONES
# =========================================================

def es_instruccion(
    linea
):

    l = normalizar_para_comparar(
        linea
    )

    if not l:
        return False

    instrucciones = [
        "seleccione la respuesta correcta",
        "selecciona la respuesta correcta",
        "seleccione lo respuesta correcta",
        "selecciona lo respuesta correcta",
        "seleccione la respuesta",
        "selecciona la respuesta",
        "elige la respuesta correcta",
        "elija la respuesta correcta",
        "marque la respuesta correcta",
        "escoja la respuesta correcta",
    ]

    # Coincidencia normal.
    if any(
        frase in l
        for frase in instrucciones
    ):
        return True

    # Regla por palabras clave, tolerante a errores como:
    # "Seleccione lo respuesta correcia".
    palabras = set(
        l.split()
    )

    tiene_verbo = any(
        p.startswith(("selecc", "elij", "elige", "marqu", "escoj"))
        for p in palabras
    )

    tiene_respuesta = any(
        p.startswith("resp")
        for p in palabras
    )

    if tiene_verbo and tiene_respuesta:
        return True

    # Comparación difusa contra las frases conocidas.
    # Umbral alto para evitar eliminar contenido médico legítimo.
    for frase in instrucciones:

        similitud = difflib.SequenceMatcher(
            None,
            l,
            frase
        ).ratio()

        if similitud >= 0.74:
            return True

    return False


# =========================================================
# BASURA SEGURA
# =========================================================

def es_fragmento_basura(
    linea
):

    texto = linea.strip()

    if not texto:

        return True

    # Solo símbolos
    if not any(
        caracter.isalnum()

        for caracter
        in texto
    ):

        return True

    # Marcador aislado
    if re.fullmatch(
        r"[\(\[\{]?\s*\d*\s*[\)\]\}\.]?",
        texto
    ):

        return True

    basura_exacta = {

        "rio",
        "tes",
        "o pr",
        "e pr",
    }

    if (
        texto.lower()
        in basura_exacta
    ):

        return True

    # No filtrar abreviaturas médicas
    # por longitud.

    return False


# =========================================================
# ENCABEZADOS
# =========================================================

def es_encabezado(
    linea
):

    l = linea.lower()

    palabras = [

        "universidad",
        "trimestral",
        "examen",
        "periodo",
        "periodo fj",
        "primer trimestral",
        "segundo trimestral",
        "tercer trimestral",
        "primer parcial",
        "segundo parcial",
        "tercer parcial",
    ]

    return any(
        palabra in l

        for palabra
        in palabras
    )


# =========================================================
# LIMPIAR OPCIONES AUTOMÁTICAS
# =========================================================

def limpiar_opciones_automaticas(
    opciones
):

    resultado = []

    for opcion in opciones:

        opcion = opcion.strip()

        if not opcion:
            continue

        # Repetir el filtro aquí porque algunos errores OCR
        # solo aparecen después de estructurar la pregunta.
        if es_instruccion(
            opcion
        ):
            continue

        if es_ruido_basico(
            opcion
        ):
            continue

        if es_fragmento_basura(
            opcion
        ):
            continue

        opcion = corregir_errores_ocr_medicos(
            opcion
        )

        # Quitar viñetas sueltas sin destruir números/abreviaturas.
        opcion = re.sub(
            r"^[\-\u2022\u25cf\u25cb]+\s*",
            "",
            opcion
        ).strip()

        if not opcion:
            continue

        # Evitar duplicados que solo difieren por espacios/mayúsculas.
        clave = normalizar_para_comparar(
            opcion
        )

        if not clave:
            continue

        claves_previas = {
            normalizar_para_comparar(x)
            for x in resultado
        }

        if clave in claves_previas:
            continue

        resultado.append(
            opcion
        )

    return resultado


# =========================================================
# LIMPIAR OPCIONES MANUALES
# =========================================================

def limpiar_opciones_manuales(
    opciones
):

    resultado = []

    for opcion in opciones:

        opcion = opcion.strip()

        if not opcion:

            continue

        if not any(
            caracter.isalnum()

            for caracter
            in opcion
        ):

            continue

        if re.fullmatch(
            r"\d+\s*[\)\.]",
            opcion
        ):

            continue

        if opcion not in resultado:

            resultado.append(
                opcion
            )

    return resultado


# =========================================================
# ESTRUCTURAR PREGUNTA
# =========================================================

def estructurar_pregunta(
    texto,
    modo="automatico"
):

    lineas = (
        limpiar_lineas(
            texto
        )
    )

    limpias = []

    # =====================================================
    # AUTOMÁTICO
    # =====================================================

    if modo == "automatico":

        for linea in lineas:

            linea = linea.strip()

            if not linea:

                continue

            if es_ruido_basico(
                linea
            ):

                continue

            limpias.append(
                linea
            )

    # =====================================================
    # MANUAL
    # =====================================================

    else:

        for linea in lineas:

            linea = linea.strip()

            if linea:

                limpias.append(
                    linea
                )

    pregunta = ""
    candidatos = []

    indice_instruccion = None

    # =====================================================
    # BUSCAR INSTRUCCIÓN
    # =====================================================

    for i, linea in enumerate(
        limpias
    ):

        if es_instruccion(
            linea
        ):

            indice_instruccion = i

            break

    # =====================================================
    # CON INSTRUCCIÓN
    # =====================================================

    if indice_instruccion is not None:

        partes = []

        for i in range(
            indice_instruccion - 1,
            -1,
            -1
        ):

            candidato = (
                limpias[i]
                .strip()
            )

            c = (
                candidato.lower()
            )

            if not candidato:

                continue

            if modo == "automatico":

                if es_fragmento_basura(
                    candidato
                ):

                    continue

                if es_encabezado(
                    candidato
                ):

                    break

                if (
                    "pregunta " in c
                    and any(
                        caracter.isdigit()

                        for caracter
                        in c
                    )
                ):

                    break

            partes.insert(
                0,
                candidato
            )

            if "¿" in candidato:

                break

            if len(partes) >= 5:

                break

        pregunta = " ".join(
            partes
        ).strip()

        candidatos = limpias[
            indice_instruccion + 1:
        ]

    # =====================================================
    # SIN INSTRUCCIÓN
    # =====================================================

    else:

        # Pregunta con ?
        for i, linea in enumerate(
            limpias
        ):

            if (
                "¿" in linea
                or
                linea.endswith("?")
            ):

                pregunta = linea

                candidatos = limpias[
                    i + 1:
                ]

                break

        # Pregunta XX
        if not pregunta:

            for i, linea in enumerate(
                limpias
            ):

                if (
                    linea.lower()
                    .startswith(
                        "pregunta "
                    )
                ):

                    if (
                        i + 1
                        < len(limpias)
                    ):

                        pregunta = (
                            limpias[
                                i + 1
                            ]
                        )

                        candidatos = (
                            limpias[
                                i + 2:
                            ]
                        )

                        break

        # Último respaldo
        if not pregunta:

            for i, linea in enumerate(
                limpias
            ):

                if modo == "automatico":

                    if es_encabezado(
                        linea
                    ):

                        continue

                    if es_fragmento_basura(
                        linea
                    ):

                        continue

                pregunta = linea

                candidatos = limpias[
                    i + 1:
                ]

                break

    # =====================================================
    # OPCIONES
    # =====================================================

    opciones_finales = []

    for opcion in candidatos:

        opcion = opcion.strip()

        if not opcion:

            continue

        # =================================================
        # AUTOMÁTICO
        # =================================================

        if modo == "automatico":

            if es_ruido_basico(
                opcion
            ):

                continue

            if es_instruccion(
                opcion
            ):

                continue

            if es_fragmento_basura(
                opcion
            ):

                continue

            if es_encabezado(
                opcion
            ):

                continue

            if opcion == pregunta:

                continue

            o = opcion.lower()

            if "1 punto" in o:

                continue

            if o == "punto":

                continue

            if (
                "pregunta " in o
                and any(
                    caracter.isdigit()

                    for caracter
                    in o
                )
            ):

                continue

        # =================================================
        # MANUAL
        # =================================================

        else:

            if es_instruccion(
                opcion
            ):

                continue

            if opcion == pregunta:

                continue

        opciones_finales.append(
            opcion
        )

    if modo == "automatico":

        pregunta = corregir_errores_ocr_medicos(
            pregunta
        )

        opciones_finales = (
            limpiar_opciones_automaticas(
                opciones_finales
            )
        )

    else:

        opciones_finales = (
            limpiar_opciones_manuales(
                opciones_finales
            )
        )

    if not pregunta:

        pregunta = (
            "No pude identificar "
            "la pregunta."
        )

    if not opciones_finales:

        opciones_finales = [
            "No pude identificar opciones."
        ]

    return (
        pregunta,
        opciones_finales
    )


# =========================================================
# PUNTUACIÓN OCR
# =========================================================

def puntuar_resultado(
    pregunta,
    opciones
):

    puntos = 0

    if pregunta:

        puntos += 2

    if (
        pregunta
        !=
        "No pude identificar la pregunta."
    ):

        puntos += 2

    if len(
        pregunta
    ) >= 8:

        puntos += 1

    opciones_validas = [

        opcion

        for opcion
        in opciones

        if (
            "No pude identificar opciones"
            not in opcion
        )
    ]

    puntos += min(
        len(opciones_validas),
        10
    )

    for opcion in opciones_validas:

        if len(opcion) >= 4:

            puntos += 0.5

    return puntos


# =========================================================
# CONFIANZA OCR
# =========================================================

def evaluar_confianza_ocr(
    pregunta,
    opciones
):

    problemas = []

    if (
        not pregunta
        or
        pregunta.startswith(
            "No pude identificar"
        )
    ):

        problemas.append(
            "pregunta no identificada"
        )

    opciones_validas = [

        opcion

        for opcion
        in opciones

        if (
            "No pude identificar opciones"
            not in opcion
        )
    ]

    if (
        opciones_validas
        and
        len(opciones_validas) < 2
    ):

        problemas.append(
            "muy pocas opciones"
        )

    if any(
        es_instruccion(opcion)
        for opcion in opciones_validas
    ):

        problemas.append(
            "instrucción confundida como opción"
        )

    # En preguntas cerradas, dos opciones o menos suelen indicar
    # un recorte/OCR incompleto. Esto fuerza la segunda pasada.
    if (
        pregunta
        and
        opciones_validas
        and
        len(opciones_validas) <= 2
    ):

        problemas.append(
            "posible pérdida de opciones"
        )

    return {

        "ok":
            len(problemas) == 0,

        "problemas":
            problemas,
    }


# =========================================================
# OCR AUTOMÁTICO INTELIGENTE
# =========================================================

def ocr_inteligente(
    imagen
):

    inicio = (
        time.perf_counter()
    )

    # =====================================================
    # PASADA 1
    # =====================================================

    texto_1 = hacer_ocr(
        imagen
    )

    (
        pregunta_1,
        opciones_1

    ) = estructurar_pregunta(
        texto_1,
        modo="automatico"
    )

    puntuacion_1 = (
        puntuar_resultado(
            pregunta_1,
            opciones_1
        )
    )

    confianza_1 = (
        evaluar_confianza_ocr(
            pregunta_1,
            opciones_1
        )
    )

    print(
        "Puntuación OCR 1:",
        puntuacion_1
    )

    print(
        "Opciones limpias OCR 1:",
        len([
            o for o in opciones_1
            if "No pude identificar opciones" not in o
        ])
    )

    if confianza_1["ok"]:

        tiempo = (
            time.perf_counter()
            - inicio
        )

        return (
            pregunta_1,
            opciones_1,
            tiempo,
            1
        )

    # =====================================================
    # PASADA 2
    # =====================================================

    print(
        "OCR 1 sospechoso:",
        confianza_1["problemas"]
    )

    texto_2 = (
        hacer_ocr_segunda_pasada(
            imagen
        )
    )

    (
        pregunta_2,
        opciones_2

    ) = estructurar_pregunta(
        texto_2,
        modo="automatico"
    )

    puntuacion_2 = (
        puntuar_resultado(
            pregunta_2,
            opciones_2
        )
    )

    print(
        "Puntuación OCR 2:",
        puntuacion_2
    )

    if puntuacion_2 > puntuacion_1:

        pregunta_final = (
            pregunta_2
        )

        opciones_finales = (
            opciones_2
        )

        pasada = 2

    else:

        pregunta_final = (
            pregunta_1
        )

        opciones_finales = (
            opciones_1
        )

        pasada = 1

    tiempo = (
        time.perf_counter()
        - inicio
    )

    return (
        pregunta_final,
        opciones_finales,
        tiempo,
        pasada
    )


# =========================================================
# OCR MANUAL
# =========================================================

def ocr_manual(
    imagen
):

    inicio = (
        time.perf_counter()
    )

    texto = hacer_ocr(
        imagen
    )

    (
        pregunta,
        opciones

    ) = estructurar_pregunta(
        texto,
        modo="manual"
    )

    tiempo = (
        time.perf_counter()
        - inicio
    )

    return (
        pregunta,
        opciones,
        tiempo
    )


# =========================================================
# PROMPT GEMINI
# =========================================================

def construir_prompt(
    pregunta,
    opciones
):

    opciones_validas = [

        opcion

        for opcion
        in opciones

        if (
            "No pude identificar opciones"
            not in opcion
        )
    ]

    if opciones_validas:

        texto_opciones = (
            "\n".join(

                f"{i}. {opcion}"

                for i, opcion
                in enumerate(
                    opciones_validas,
                    start=1
                )
            )
        )

        return f"""
Pregunta:
{pregunta}

Opciones:
{texto_opciones}

Elige UNA sola mejor respuesta.

Comprueba internamente que el número
corresponda exactamente con la opción elegida.

Devuelve únicamente:

TIPO: OPCION
NUMERO: <número>
CONFIANZA: <entero 0-100>
EXPLICACION: <máximo 18 palabras>

La CONFIANZA debe reflejar qué tan seguro estás de que esa opción
es correcta CON LA INFORMACIÓN RECIBIDA. Si el texto/OCR parece
incompleto o ambiguo, reduce la confianza.
"""

    return f"""
Pregunta:
{pregunta}

Devuelve únicamente:

TIPO: ABIERTA
RESPUESTA: <máximo 25 palabras>
CONFIANZA: <entero 0-100>
EXPLICACION: <máximo 18 palabras>
"""


# =========================================================
# ERRORES TEMPORALES GEMINI
# =========================================================

def es_error_temporal_gemini(error):

    texto = str(error).lower()

    indicadores = [
        "503",
        "unavailable",
        "temporarily unavailable",
        "spikes in demand",
        "try again later",
        "resource exhausted",
        "429",
    ]

    return any(
        indicador in texto
        for indicador in indicadores
    )


# =========================================================
# CONSULTAR GEMINI
# =========================================================

def consultar_gemini(
    pregunta,
    opciones
):

    if gemini_client is None:
        return (
            "ERROR: Gemini no está configurado."
        )

    prompt = construir_prompt(
        pregunta,
        opciones
    )

    modelo = obtener_modelo_gemini()

    print(
        "\n===== GEMINI ====="
    )

    print(
        "Modelo:",
        modelo
    )

    intentos_maximos = 3

    for intento in range(
        1,
        intentos_maximos + 1
    ):

        try:

            inicio = time.perf_counter()

            respuesta = (
                gemini_client
                .models
                .generate_content(
                    model=modelo,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        thinking_config=
                            types.ThinkingConfig(
                                thinking_level="minimal"
                            ),
                        max_output_tokens=50
                    )
                )
            )

            tiempo = (
                time.perf_counter()
                - inicio
            )

            if not respuesta.text:
                return (
                    "ERROR: Gemini no devolvió texto."
                )

            resultado = (
                respuesta.text.strip()
            )

            print(
                resultado
            )

            print(
                f"Gemini: {tiempo:.2f} s"
            )

            print(
                "==================\n"
            )

            return resultado

        except Exception as e:

            print(
                f"Gemini intento {intento}/{intentos_maximos}:",
                e
            )

            if (
                es_error_temporal_gemini(e)
                and intento < intentos_maximos
            ):

                espera = (
                    0.8
                    if intento == 1
                    else 1.5
                )

                print(
                    f"Error temporal. Reintentando en {espera:.1f} s..."
                )

                time.sleep(
                    espera
                )

                continue

            return (
                "ERROR GEMINI:\n"
                + str(e)
            )

    return (
        "ERROR GEMINI: sin respuesta."
    )


# =========================================================
# CONSULTAR OPENAI
# =========================================================

def consultar_openai(
    pregunta,
    opciones
):

    if openai_client is None:
        return "ERROR: OpenAI no está configurado."

    try:
        prompt = construir_prompt(
            pregunta,
            opciones
        )

        print("\n===== OPENAI =====")
        print("Modelo:", OPENAI_MODEL)

        inicio = time.perf_counter()

        respuesta = openai_client.responses.create(
            model=OPENAI_MODEL,
            input=prompt,
            max_output_tokens=140
        )

        tiempo = time.perf_counter() - inicio
        resultado = (respuesta.output_text or "").strip()

        if not resultado:
            return "ERROR: OpenAI no devolvió texto."

        print(resultado)
        print(f"OpenAI: {tiempo:.2f} s")
        print("==================\n")

        return resultado

    except Exception as e:
        print("Error OpenAI:", e)
        codigo, mensaje = interpretar_error_openai(e)

        if codigo == "SIN_CUOTA":
            return (
                "ERROR OPENAI: SIN_CUOTA\n"
                "La API de OpenAI no tiene cuota/crédito disponible. "
                "Puedes cambiar a Gemini desde Ctrl+0."
            )

        return "ERROR OPENAI:\n" + mensaje


# =========================================================
# CONFIANZA / REVISIÓN AUTOMÁTICA
# =========================================================

def obtener_confianza_respuesta(
    respuesta,
    opciones=None
):

    try:
        datos = interpretar_respuesta_gemini(
            respuesta,
            opciones
        )

        valor = datos.get(
            "confianza",
            ""
        )

        if str(valor).isdigit():
            return int(valor)

    except Exception:
        pass

    return None


def respuesta_necesita_revision(
    respuesta,
    opciones
):

    confianza = obtener_confianza_respuesta(
        respuesta,
        opciones
    )

    if confianza is None:
        return False

    return confianza < (
        CONFIANZA_FALLBACK_PRECISO
    )


# =========================================================
# CONSULTAR PROVEEDOR SELECCIONADO
# =========================================================

def consultar_ia(
    pregunta,
    opciones
):

    # OpenAI usa su propio proveedor sin fallback de Gemini.
    if PROVEEDOR_IA == "openai":
        return consultar_openai(
            pregunta,
            opciones
        )

    respuesta = consultar_gemini(
        pregunta,
        opciones
    )

    # En modo Rápido, si el propio modelo reporta baja confianza,
    # hacemos UNA segunda comprobación con el modelo Preciso.
    if (
        GEMINI_MODO == "rapido"
        and not respuesta.startswith("ERROR")
        and respuesta_necesita_revision(
            respuesta,
            opciones
        )
    ):

        confianza = obtener_confianza_respuesta(
            respuesta,
            opciones
        )

        print(
            f"Confianza baja ({confianza}%). "
            "Revisando con Gemini preciso..."
        )

        try:
            modelo_anterior = GEMINI_MODO

            # Llamada directa con modelo preciso para no cambiar
            # permanentemente la preferencia del usuario.
            prompt = construir_prompt(
                pregunta,
                opciones
            )

            inicio = time.perf_counter()

            revision = (
                gemini_client
                .models
                .generate_content(
                    model=GEMINI_MODEL_PRECISO,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        thinking_config=
                            types.ThinkingConfig(
                                thinking_level="minimal"
                            ),
                        max_output_tokens=70
                    )
                )
            )

            resultado_revision = (
                revision.text or ""
            ).strip()

            if resultado_revision:

                print(
                    "Revisión precisa:",
                    resultado_revision
                )

                return resultado_revision

        except Exception as e:

            print(
                "No pude realizar revisión precisa:",
                e
            )

    return respuesta


# =========================================================
# INTERPRETAR GEMINI
# =========================================================

def interpretar_respuesta_gemini(
    texto,
    opciones=None
):

    resultado = {

        "tipo": "",
        "numero": "",
        "respuesta": "",
        "confianza": "",
        "explicacion": "",
    }

    if not texto:

        return resultado

    for linea in (
        texto.splitlines()
    ):

        linea = linea.strip()

        if not linea:

            continue

        mayuscula = (
            linea.upper()
        )

        if mayuscula.startswith(
            "TIPO:"
        ):

            resultado["tipo"] = (
                linea.split(
                    ":",
                    1
                )[1]
                .strip()
                .upper()
            )

        elif (
            mayuscula.startswith(
                "NUMERO:"
            )

            or

            mayuscula.startswith(
                "NÚMERO:"
            )
        ):

            resultado["numero"] = (
                linea.split(
                    ":",
                    1
                )[1]
                .strip()
            )

        elif mayuscula.startswith(
            "CONFIANZA:"
        ):

            valor = linea.split(
                ":",
                1
            )[1].strip()

            coincidencia = re.search(
                r"\d{1,3}",
                valor
            )

            if coincidencia:
                numero_conf = max(
                    0,
                    min(
                        100,
                        int(coincidencia.group())
                    )
                )

                resultado["confianza"] = str(
                    numero_conf
                )

        elif mayuscula.startswith(
            "RESPUESTA:"
        ):

            resultado[
                "respuesta"
            ] = (
                linea.split(
                    ":",
                    1
                )[1]
                .strip()
            )

        elif (
            mayuscula.startswith(
                "EXPLICACION:"
            )

            or

            mayuscula.startswith(
                "EXPLICACIÓN:"
            )
        ):

            resultado[
                "explicacion"
            ] = (
                linea.split(
                    ":",
                    1
                )[1]
                .strip()
            )

    if (
        resultado["tipo"]
        == "OPCION"

        and opciones
    ):

        coincidencia = re.search(
            r"\d+",
            resultado["numero"]
        )

        if coincidencia:

            numero = int(
                coincidencia.group()
            )

            if (
                1 <= numero
                <= len(opciones)
            ):

                resultado[
                    "numero"
                ] = str(
                    numero
                )

                resultado[
                    "respuesta"
                ] = opciones[
                    numero - 1
                ]

            else:

                resultado[
                    "numero"
                ] = ""

    return resultado


# =========================================================
# RESULTADO COMPACTO
# =========================================================

def mostrar_resultado_compacto(
    respuesta_gemini,
    opciones,
    pregunta=""
):

    global ultima_respuesta_gemini
    global ultimo_resultado_corto
    global ultimas_opciones
    global ultima_pregunta_detectada

    ultima_respuesta_gemini = (
        respuesta_gemini
    )

    ultimas_opciones = (
        opciones
    )

    if pregunta:
        ultima_pregunta_detectada = str(pregunta).strip()

    datos = (
        interpretar_respuesta_gemini(
            respuesta_gemini,
            opciones
        )
    )

    tipo = datos[
        "tipo"
    ]

    numero = datos[
        "numero"
    ]

    if (
        tipo == "OPCION"
        and numero
    ):

        corto = numero

    elif tipo == "ABIERTA":

        corto = "R"

    elif respuesta_gemini.startswith(
        "ERROR"
    ):

        corto = "!"

    else:

        corto = "?"

    ultimo_resultado_corto = (
        corto
    )

    boton.config(
        image="",
        text=corto,

        font=(
            "Segoe UI",
            11
            if modo_compacto
            else 20,
            "bold"
        )
    )

    root.after(
        TIEMPO_RESPUESTA,
        restaurar_icono
    )


# =========================================================
# DETALLE DE RESPUESTA
# =========================================================

def mostrar_detalle_respuesta(
    event=None
):

    global ventana_detalle
    global ultima_pregunta_detectada

    if not ultima_respuesta_gemini:

        return

    if ventana_detalle is not None:

        try:

            if (
                ventana_detalle
                .winfo_exists()
            ):

                return

        except Exception:

            pass

    datos = (
        interpretar_respuesta_gemini(
            ultima_respuesta_gemini,
            ultimas_opciones
        )
    )

    ventana_detalle = (
        tk.Toplevel(
            root
        )
    )

    ventana_detalle.overrideredirect(
        True
    )

    ventana_detalle.attributes(
        "-topmost",
        True
    )

    # Casi sin color, como las primeras versiones.
    try:
        ventana_detalle.attributes(
            "-alpha",
            0.94
        )
    except Exception:
        pass

    x = (
        root.winfo_x()
        - 350
    )

    y = (
        root.winfo_y()
        - 10
    )

    if x < 10:

        x = (
            root.winfo_x()
            + root.winfo_width()
            + 10
        )

    if y < 10:

        y = 10

    ventana_detalle.geometry(
        f"340x285+{x}+{y}"
    )

    marco = tk.Frame(
        ventana_detalle,
        bg="#F4F4F4",
        bd=1,
        relief="solid"
    )

    marco.pack(
        fill="both",
        expand=True
    )

    if datos.get("numero"):

        titulo = (
            "Respuesta "
            + datos["numero"]
        )

    else:

        titulo = (
            "Respuesta"
        )

    tk.Label(
        marco,
        text=titulo,
        bg="#F4F4F4",
        fg="#111111",
        font=(
            "Segoe UI",
            11,
            "bold"
        )
    ).pack(
        anchor="w",
        padx=10,
        pady=(8, 4)
    )

    # ÚNICO AÑADIDO VISUAL:
    # mostrar el texto que el OCR detectó como pregunta.
    if ultima_pregunta_detectada:

        tk.Label(
            marco,
            text="Pregunta detectada:",
            bg="#F4F4F4",
            fg="#333333",
            font=(
                "Segoe UI",
                8,
                "bold"
            )
        ).pack(
            anchor="w",
            padx=10,
            pady=(2, 1)
        )

        tk.Label(
            marco,
            text=ultima_pregunta_detectada,
            bg="#F4F4F4",
            fg="#222222",
            font=(
                "Segoe UI",
                8
            ),
            justify="left",
            wraplength=315
        ).pack(
            anchor="w",
            padx=10,
            pady=(0, 6)
        )

    respuesta = (
        datos.get("respuesta")
        or
        ultima_respuesta_gemini
    )

    tk.Label(
        marco,
        text=respuesta,
        bg="#F4F4F4",
        fg="#111111",
        font=(
            "Segoe UI",
            10
        ),
        justify="left",
        wraplength=315
    ).pack(
        anchor="w",
        padx=10
    )

    if datos.get("confianza"):

        tk.Label(
            marco,
            text=(
                "Confianza IA: "
                + str(
                    datos["confianza"]
                )
                + "%"
            ),
            bg="#F4F4F4",
            fg="#333333",
            font=(
                "Segoe UI",
                9
            )
        ).pack(
            anchor="w",
            padx=10,
            pady=(8, 0)
        )

    if datos.get("explicacion"):

        tk.Label(
            marco,
            text="Explicación:",
            bg="#F4F4F4",
            fg="#111111",
            font=(
                "Segoe UI",
                9,
                "bold"
            )
        ).pack(
            anchor="w",
            padx=10,
            pady=(10, 2)
        )

        tk.Label(
            marco,
            text=datos[
                "explicacion"
            ],
            bg="#F4F4F4",
            fg="#222222",
            font=(
                "Segoe UI",
                9
            ),
            justify="left",
            wraplength=315
        ).pack(
            anchor="w",
            padx=10
        )


# =========================================================
# OCULTAR DETALLE
# =========================================================

def ocultar_detalle_respuesta(
    event=None
):

    global ventana_detalle

    if ventana_detalle is not None:

        try:

            ventana_detalle.destroy()

        except Exception:

            pass

        ventana_detalle = None


# =========================================================
# PROCESAR AUTOMÁTICO
# =========================================================

def procesar_imagen_automatica(
    imagen,
    titulo
):

    inicio_total = (
        time.perf_counter()
    )

    (
        pregunta,
        opciones,
        tiempo_ocr,
        pasada

    ) = ocr_inteligente(
        imagen
    )

    print(
        "\n=============================="
    )

    print(
        "MODO: AUTOMÁTICO"
    )

    print(
        "OCR elegido:",
        pasada
    )

    print(
        "PREGUNTA:"
    )

    print(
        pregunta
    )

    print(
        "\nOPCIONES:"
    )

    for opcion in opciones:

        print(
            "-",
            opcion
        )

    print(
        "=============================="
    )

    confianza = (
        evaluar_confianza_ocr(
            pregunta,
            opciones
        )
    )

    if not confianza["ok"]:

        root.after(
            0,

            lambda:
                mostrar_resultado_compacto(
                    "ERROR: OCR incompleto",
                    opciones
                )
        )

        return

    inicio_ia = (
        time.perf_counter()
    )

    respuesta = (
        consultar_ia(
            pregunta,
            opciones
        )
    )

    tiempo_ia = (
        time.perf_counter()
        - inicio_ia
    )

    confianza_ia = obtener_confianza_respuesta(
        respuesta,
        opciones
    )

    if confianza_ia is not None:
        print(
            f"Confianza IA: {confianza_ia}%"
        )

    tiempo_total = (
        time.perf_counter()
        - inicio_total
    )

    print(
        "\n===== TIEMPOS ====="
    )

    print(
        f"OCR:    "
        f"{tiempo_ocr:.2f} s"
    )

    print(
        f"IA ({nombre_proveedor_actual()}): "
        f"{tiempo_ia:.2f} s"
    )

    print(
        f"TOTAL:  "
        f"{tiempo_total:.2f} s"
    )

    print(
        "===================\n"
    )

    guardar_en_historial(
        pregunta,
        opciones,
        respuesta,
        fuente="Automático"
    )

    root.after(
        0,

        lambda:
            mostrar_resultado_compacto(
                respuesta,
                opciones,
                pregunta
            )
    )


# =========================================================
# PROCESAR MANUAL
# =========================================================

def procesar_imagen_manual(
    imagen,
    titulo,
    fuente="Manual"
):

    inicio_total = (
        time.perf_counter()
    )

    (
        pregunta,
        opciones,
        tiempo_ocr

    ) = ocr_manual(
        imagen
    )

    print(
        "\n=============================="
    )

    print(
        "MODO: MANUAL"
    )

    print(
        "PREGUNTA:"
    )

    print(
        pregunta
    )

    print(
        "\nOPCIONES:"
    )

    for opcion in opciones:

        print(
            "-",
            opcion
        )

    print(
        "=============================="
    )

    inicio_ia = (
        time.perf_counter()
    )

    respuesta = (
        consultar_ia(
            pregunta,
            opciones
        )
    )

    tiempo_ia = (
        time.perf_counter()
        - inicio_ia
    )

    confianza_ia = obtener_confianza_respuesta(
        respuesta,
        opciones
    )

    if confianza_ia is not None:
        print(
            f"Confianza IA: {confianza_ia}%"
        )

    tiempo_total = (
        time.perf_counter()
        - inicio_total
    )

    print(
        "\n===== TIEMPOS MANUAL ====="
    )

    print(
        f"OCR:    "
        f"{tiempo_ocr:.2f} s"
    )

    print(
        f"IA ({nombre_proveedor_actual()}): "
        f"{tiempo_ia:.2f} s"
    )

    print(
        f"TOTAL:  "
        f"{tiempo_total:.2f} s"
    )

    print(
        "==========================\n"
    )

    guardar_en_historial(
        pregunta,
        opciones,
        respuesta,
        fuente=fuente
    )

    root.after(
        0,

        lambda:
            mostrar_resultado_compacto(
                respuesta,
                opciones,
                pregunta
            )
    )


# =========================================================
# ANALIZAR AUTOMÁTICO
# =========================================================

def analizar_zona_guardada(
    event=None
):

    if not asegurar_licencia():
        return

    if not proveedor_configurado():

        abrir_configuracion_proveedor_actual(
            obligatoria=False
        )

        return

    if not ultima_ventana:

        mostrar_mensaje_temporal(
            "?"
        )

        return

    if zona_guardada is None:

        mostrar_mensaje_temporal(
            "⚙"
        )

        root.after(
            500,
            configurar_zona
        )

        return

    hwnd = (
        ultima_ventana
    )

    titulo = (
        ultimo_titulo
    )

    boton.config(

        image="",
        text="...",

        font=(
            "Segoe UI",
            10
            if modo_compacto
            else 14,
            "bold"
        )
    )

    def tarea():

        captura = (
            capturar_ventana(
                hwnd
            )
        )

        if captura is None:

            root.after(
                0,

                lambda:
                    mostrar_resultado_compacto(
                        "ERROR: captura",
                        []
                    )
            )

            return

        ancho, alto = (
            captura.size
        )

        x1 = int(
            ancho
            * zona_guardada["x1"]
        )

        y1 = int(
            alto
            * zona_guardada["y1"]
        )

        x2 = int(
            ancho
            * zona_guardada["x2"]
        )

        y2 = int(
            alto
            * zona_guardada["y2"]
        )

        recorte = (
            captura.crop(
                (
                    x1,
                    y1,
                    x2,
                    y2
                )
            )
        )

        procesar_imagen_automatica(
            recorte,
            titulo
        )

    threading.Thread(
        target=tarea,
        daemon=True
    ).start()


# =========================================================
# CONFIGURAR MARCO
# =========================================================

def configurar_zona(
    event=None
):

    if not ultima_ventana:

        mostrar_mensaje_temporal(
            "?"
        )

        return

    rect = (
        obtener_rectangulo_ventana(
            ultima_ventana
        )
    )

    if rect is None:

        return

    root.withdraw()

    root.after(
        150,

        lambda:
            selector_zona(
                guardar=True,
                ventana_rect=rect
            )
    )


# =========================================================
# MODO MANUAL
# =========================================================

def modo_manual(
    event=None
):

    if not asegurar_licencia():
        return

    if not proveedor_configurado():

        abrir_configuracion_proveedor_actual(
            obligatoria=False
        )

        return

    root.withdraw()

    root.after(
        150,

        lambda:
            selector_zona(
                guardar=False,
                ventana_rect=None
            )
    )


# =========================================================
# SELECTOR DE ZONA
# =========================================================

def selector_zona(
    guardar,
    ventana_rect
):

    selector = (
        tk.Toplevel()
    )

    selector.attributes(
        "-fullscreen",
        True
    )

    selector.attributes(
        "-topmost",
        True
    )

    selector.attributes(
        "-alpha",
        0.30
    )

    selector.configure(
        bg="black"
    )

    canvas = tk.Canvas(

        selector,

        cursor="cross",
        bg="black",
        highlightthickness=0
    )

    canvas.pack(
        fill="both",
        expand=True
    )

    datos = {

        "x1": 0,
        "y1": 0,

        "x2": 0,
        "y2": 0,

        "rect": None
    }

    def empezar(
        event
    ):

        datos["x1"] = (
            event.x
        )

        datos["y1"] = (
            event.y
        )

        datos["rect"] = (
            canvas.create_rectangle(

                event.x,
                event.y,

                event.x,
                event.y,

                outline="white",
                width=3
            )
        )

    def mover(
        event
    ):

        if datos["rect"]:

            canvas.coords(

                datos["rect"],

                datos["x1"],
                datos["y1"],

                event.x,
                event.y
            )

    def terminar(
        event
    ):

        datos["x2"] = (
            event.x
        )

        datos["y2"] = (
            event.y
        )

        x1 = min(
            datos["x1"],
            datos["x2"]
        )

        y1 = min(
            datos["y1"],
            datos["y2"]
        )

        x2 = max(
            datos["x1"],
            datos["x2"]
        )

        y2 = max(
            datos["y1"],
            datos["y2"]
        )

        selector.destroy()

        root.deiconify()

        if (
            x2 - x1 < 20
            or
            y2 - y1 < 20
        ):

            return

        # =================================================
        # GUARDAR MARCO AUTOMÁTICO
        # =================================================

        if guardar:

            (
                izquierda,
                arriba,
                derecha,
                abajo

            ) = ventana_rect

            ancho = (
                derecha
                - izquierda
            )

            alto = (
                abajo
                - arriba
            )

            zona = {

                "x1":
                    max(
                        0,
                        min(
                            1,

                            (
                                x1
                                - izquierda
                            )
                            / ancho
                        )
                    ),

                "y1":
                    max(
                        0,
                        min(
                            1,

                            (
                                y1
                                - arriba
                            )
                            / alto
                        )
                    ),

                "x2":
                    max(
                        0,
                        min(
                            1,

                            (
                                x2
                                - izquierda
                            )
                            / ancho
                        )
                    ),

                "y2":
                    max(
                        0,
                        min(
                            1,

                            (
                                y2
                                - arriba
                            )
                            / alto
                        )
                    )
            }

            guardar_configuracion(
                zona
            )

            mostrar_mensaje_temporal(
                "✓"
            )

            return

        # =================================================
        # MANUAL
        # =================================================

        boton.config(

            image="",
            text="...",

            font=(
                "Segoe UI",
                10
                if modo_compacto
                else 14,
                "bold"
            )
        )

        def tarea_manual():

            try:

                captura = (
                    ImageGrab.grab(

                        bbox=(
                            x1,
                            y1,
                            x2,
                            y2
                        ),

                        all_screens=True
                    )
                )

                procesar_imagen_manual(
                    captura,
                    "Selección manual"
                )

            except Exception as e:

                root.after(
                    0,

                    lambda:
                        mostrar_resultado_compacto(

                            "ERROR:\n"
                            + str(e),

                            []
                        )
                )

        threading.Thread(
            target=tarea_manual,
            daemon=True
        ).start()

    def cancelar(
        event=None
    ):

        selector.destroy()

        root.deiconify()

    canvas.bind(
        "<ButtonPress-1>",
        empezar
    )

    canvas.bind(
        "<B1-Motion>",
        mover
    )

    canvas.bind(
        "<ButtonRelease-1>",
        terminar
    )

    selector.bind(
        "<Escape>",
        cancelar
    )


# =========================================================
# MODO COMPACTO
# =========================================================

def alternar_modo_compacto(
    event=None
):

    global modo_compacto

    modo_compacto = not modo_compacto

    x = root.winfo_x()
    y = root.winfo_y()

    if modo_compacto:

        root.geometry(
            f"{TAMANO_COMPACTO}"
            f"x{TAMANO_COMPACTO}"
            f"+{x}+{y}"
        )

        root.attributes(
            "-alpha",
            OPACIDAD_COMPACTO
        )

        boton.config(
            image="",
            text="●",
            font=(
                "Segoe UI",
                7,
                "bold"
            )
        )

    else:

        root.geometry(
            f"{TAMANO_NORMAL}"
            f"x{TAMANO_NORMAL}"
            f"+{x}+{y}"
        )

        root.attributes(
            "-alpha",
            1.0
        )

        restaurar_icono()

# =========================================================
# ARRASTRAR MASTERX
# =========================================================

def iniciar_arrastre(
    event
):

    arrastre[
        "offset_x"
    ] = event.x

    arrastre[
        "offset_y"
    ] = event.y

    arrastre[
        "inicio_x"
    ] = event.x_root

    arrastre[
        "inicio_y"
    ] = event.y_root

    arrastre[
        "movido"
    ] = False


def mover_masterx(
    event
):

    diferencia_x = (
        event.x_root
        - arrastre["inicio_x"]
    )

    diferencia_y = (
        event.y_root
        - arrastre["inicio_y"]
    )

    if (
        abs(diferencia_x) > 5
        or
        abs(diferencia_y) > 5
    ):

        arrastre[
            "movido"
        ] = True

    if not arrastre[
        "movido"
    ]:

        return

    nueva_x = (
        event.x_root
        - arrastre["offset_x"]
    )

    nueva_y = (
        event.y_root
        - arrastre["offset_y"]
    )

    root.geometry(
        f"+{nueva_x}+{nueva_y}"
    )


def terminar_arrastre(
    event
):

    global posicion_x
    global posicion_y

    if arrastre["movido"]:

        posicion_x = (
            root.winfo_x()
        )

        posicion_y = (
            root.winfo_y()
        )

        guardar_estado()

        return

    analizar_zona_guardada()


# =========================================================
# MENSAJE TEMPORAL
# =========================================================

def mostrar_mensaje_temporal(
    texto
):

    boton.config(

        image="",
        text=texto,

        font=(
            "Segoe UI",

            10
            if modo_compacto
            else 17,

            "bold"
        )
    )

    root.after(
        1000,
        restaurar_icono
    )


# =========================================================
# RESTAURAR ICONO
# =========================================================

def restaurar_icono():

    if modo_compacto:

        boton.config(

            image="",
            text="●",

            font=(
                "Segoe UI",
                8,
                "bold"
            )
        )

    else:

        boton.config(
            image=imagen_tk,
            text=""
        )


# =========================================================
# LICENCIAS MASTERX
# =========================================================

def normalizar_licencia(clave):

    if clave is None:
        return ""

    return re.sub(
        r"[^A-Za-z0-9]",
        "",
        str(clave)
    ).upper()


def obtener_id_dispositivo():

    """
    Genera un ID estable, pseudónimo y no reversible a partir
    de datos básicos del equipo. Al servidor SOLO se envía el hash.
    """

    base = "|".join([
        platform.system(),
        platform.machine(),
        platform.node(),
        str(uuid.getnode())
    ])

    return hashlib.sha256(
        base.encode("utf-8", errors="ignore")
    ).hexdigest()


def validar_formato_licencia(clave):

    clave = normalizar_licencia(clave)

    return (
        len(clave) == LICENCIA_LONGITUD
        and clave.isalnum()
    )


def licencia_online_configurada():

    return bool(
        str(LICENSE_SERVER_URL or "").strip()
    )


def validar_licencia_online(clave):

    """
    Devuelve:
        (ok, datos)

    datos siempre es un diccionario.
    """

    clave = normalizar_licencia(clave)

    if not validar_formato_licencia(clave):
        return False, {
            "message": "La licencia debe tener 12 caracteres alfanuméricos."
        }

    payload = json.dumps({
        "license": clave,
        "device_id": obtener_id_dispositivo(),
        "app": "MasterX",
        "version": "Beta 3"
    }).encode("utf-8")

    solicitud = urllib.request.Request(
        LICENSE_SERVER_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "MasterX-Beta3"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(
            solicitud,
            timeout=LICENSE_TIMEOUT
        ) as respuesta:

            cuerpo = respuesta.read().decode(
                "utf-8",
                errors="replace"
            )

            datos = json.loads(cuerpo or "{}")

            return bool(datos.get("valid")), datos

    except urllib.error.HTTPError as e:

        try:
            cuerpo = e.read().decode(
                "utf-8",
                errors="replace"
            )
            datos = json.loads(cuerpo or "{}")
        except Exception:
            datos = {
                "message": f"Servidor respondió HTTP {e.code}."
            }

        return False, datos

    except Exception as e:

        return False, {
            "offline": True,
            "message": str(e)
        }


def licencia_tiene_gracia_offline():

    if licencia_estado != "online":
        return False

    if not licencia_ultima_validacion:
        return False

    segundos = (
        time.time()
        - licencia_ultima_validacion
    )

    return segundos <= (
        LICENSE_OFFLINE_GRACE_HOURS
        * 3600
    )


def validar_licencia(clave):

    """
    Validación usada al cargar configuración.

    - Sin servidor: modo beta local.
    - Con servidor: solo considera activa una licencia previamente
      validada online y dentro del periodo offline permitido.
    """

    clave = normalizar_licencia(clave)

    if not validar_formato_licencia(clave):
        return False

    if not licencia_online_configurada():
        return True

    return licencia_tiene_gracia_offline()


def activar_licencia(clave):

    global licencia_clave
    global licencia_activa
    global licencia_estado
    global licencia_expira
    global licencia_ultima_validacion

    normalizada = normalizar_licencia(clave)

    if not validar_formato_licencia(normalizada):
        return False, (
            "Licencia inválida: deben ser "
            "12 caracteres alfanuméricos."
        )

    # =====================================================
    # BETA LOCAL
    # =====================================================

    if not licencia_online_configurada():

        licencia_clave = normalizada
        licencia_activa = True
        licencia_estado = "local"
        licencia_expira = ""
        licencia_ultima_validacion = time.time()

        guardar_estado()

        return True, (
            "Licencia beta local activada."
        )

    # =====================================================
    # SERVIDOR
    # =====================================================

    ok, datos = validar_licencia_online(
        normalizada
    )

    if ok:

        licencia_clave = normalizada
        licencia_activa = True
        licencia_estado = "online"
        licencia_expira = str(
            datos.get("expires", "")
        )
        licencia_ultima_validacion = time.time()

        guardar_estado()

        return True, str(
            datos.get(
                "message",
                "Licencia validada online."
            )
        )

    # Si no hubo red, permitir gracia SOLO a una licencia ya validada
    # anteriormente en ese mismo equipo.
    if (
        datos.get("offline")
        and normalizada == licencia_clave
        and licencia_tiene_gracia_offline()
    ):

        licencia_activa = True

        return True, (
            "Servidor no disponible. "
            "Usando validación offline temporal."
        )

    licencia_activa = False

    return False, str(
        datos.get(
            "message",
            "Licencia rechazada por el servidor."
        )
    )


def licencia_mostrada():

    if not licencia_clave:
        return "No activada"

    return (
        licencia_clave[:4]
        + "-"
        + licencia_clave[4:8]
        + "-"
        + licencia_clave[8:12]
    )


def texto_estado_licencia():

    if not licencia_activa:
        return "Licencia no activada"

    if licencia_estado == "online":
        extra = (
            f" · vence {licencia_expira}"
            if licencia_expira
            else ""
        )
        return f"Licencia online activa ✓{extra}"

    return "Licencia beta local activa ✓"


def abrir_configuracion_licencia(
    event=None,
    obligatoria=False,
    al_terminar=None
):

    global ventana_licencia

    if ventana_licencia is not None:
        try:
            if ventana_licencia.winfo_exists():
                ventana_licencia.lift()
                return
        except Exception:
            pass

    ventana_licencia = tk.Toplevel(root)
    ventana_licencia.title("MasterX - Licencia")
    ventana_licencia.geometry("460x310")
    ventana_licencia.resizable(False, False)
    ventana_licencia.attributes("-topmost", True)
    colorear_barra_titulo(
        ventana_licencia,
        fondo="#0D0B18",
        texto="#EAF9FF",
        borde="#45D4FF"
    )

    AZUL_FONDO = "#050B18"
    AZUL_PANEL = "#08182D"
    AZUL_BORDE = "#007BFF"
    AZUL_BOTON = "#0066CC"
    BLANCO = "#F4FAFF"
    GRIS = "#9CC9E8"
    VERDE = "#28E6A7"
    ROJO = "#FF4D6D"

    ventana_licencia.configure(bg=AZUL_BORDE)

    fondo = tk.Frame(
        ventana_licencia,
        bg=AZUL_FONDO
    )
    fondo.pack(
        fill="both",
        expand=True,
        padx=3,
        pady=3
    )

    tk.Label(
        fondo,
        text="MasterX",
        bg=AZUL_FONDO,
        fg=BLANCO,
        font=("Segoe UI", 17, "bold")
    ).pack(pady=(20, 2))

    tk.Label(
        fondo,
        text="Activación de licencia",
        bg=AZUL_FONDO,
        fg=GRIS,
        font=("Segoe UI", 10)
    ).pack(pady=(0, 8))

    modo_txt = (
        "Servidor de licencias"
        if licencia_online_configurada()
        else "Modo beta local"
    )

    tk.Label(
        fondo,
        text=modo_txt,
        bg=AZUL_FONDO,
        fg="#00D9FF",
        font=("Segoe UI", 8, "bold")
    ).pack(pady=(0, 12))

    variable = tk.StringVar(
        value=licencia_mostrada() if licencia_clave else ""
    )

    entrada = tk.Entry(
        fondo,
        textvariable=variable,
        justify="center",
        bg=AZUL_PANEL,
        fg=BLANCO,
        insertbackground=BLANCO,
        relief="flat",
        highlightthickness=1,
        highlightbackground=AZUL_BORDE,
        highlightcolor="#00D9FF",
        font=("Consolas", 13, "bold")
    )
    entrada.pack(
        fill="x",
        padx=35,
        ipady=7
    )
    entrada.focus_set()

    estado = tk.Label(
        fondo,
        text=texto_estado_licencia(),
        bg=AZUL_FONDO,
        fg=(VERDE if licencia_activa else GRIS),
        font=("Segoe UI", 9, "bold"),
        wraplength=390,
        justify="center"
    )
    estado.pack(pady=12)

    def cerrar_licencia():

        global ventana_licencia

        if obligatoria and not licencia_activa:
            respuesta = messagebox.askyesno(
                "MasterX",
                (
                    "MasterX necesita una licencia para continuar.\n\n"
                    "¿Quieres cerrar MasterX?"
                ),
                parent=ventana_licencia
            )

            if respuesta:
                ventana_licencia.destroy()
                ventana_licencia = None
                cerrar_masterx()

            return

        ventana_licencia.destroy()
        ventana_licencia = None

    def activar():

        global ventana_licencia

        estado.config(
            text="Verificando licencia...",
            fg="#00D9FF"
        )
        ventana_licencia.update_idletasks()

        clave = variable.get()

        def tarea():

            ok, mensaje = activar_licencia(
                clave
            )

            root.after(
                0,
                lambda: finalizar(
                    ok,
                    mensaje
                )
            )

        threading.Thread(
            target=tarea,
            daemon=True
        ).start()

    def finalizar(ok, mensaje):

        global ventana_licencia

        if not ok:
            estado.config(
                text=mensaje,
                fg=ROJO
            )
            return

        estado.config(
            text=texto_estado_licencia(),
            fg=VERDE
        )

        messagebox.showinfo(
            "MasterX",
            mensaje,
            parent=ventana_licencia
        )

        ventana_licencia.destroy()
        ventana_licencia = None

        if callable(al_terminar):
            root.after(
                150,
                al_terminar
            )

    ventana_licencia.protocol(
        "WM_DELETE_WINDOW",
        cerrar_licencia
    )

    botones = tk.Frame(
        fondo,
        bg=AZUL_FONDO
    )
    botones.pack(pady=(2, 0))

    tk.Button(
        botones,
        text="Activar",
        command=activar,
        bg=AZUL_BOTON,
        fg=BLANCO,
        activebackground=AZUL_BORDE,
        activeforeground=BLANCO,
        relief="flat",
        borderwidth=0,
        padx=18,
        pady=6,
        cursor="hand2",
        font=("Segoe UI", 9, "bold")
    ).pack(side="right")

    if not obligatoria:
        tk.Button(
            botones,
            text="Cerrar",
            command=cerrar_licencia,
            bg=AZUL_PANEL,
            fg=BLANCO,
            activebackground=AZUL_BOTON,
            activeforeground=BLANCO,
            relief="flat",
            borderwidth=0,
            padx=18,
            pady=6,
            cursor="hand2"
        ).pack(side="right", padx=8)


def asegurar_licencia():

    if licencia_activa:
        return True

    abrir_configuracion_licencia(
        obligatoria=False
    )

    return False


# =========================================================
# GOOGLE AI STUDIO
# =========================================================

def abrir_pagina_api_google():

    try:
        webbrowser.open(
            "https://aistudio.google.com/app/apikey"
        )
    except Exception as e:
        messagebox.showerror(
            "MasterX",
            "No pude abrir el navegador.\n\n" + str(e)
        )


# =========================================================
# VENTANA CONFIGURAR API
# =========================================================

def abrir_configuracion_api(
    event=None,
    obligatoria=False
):

    global ventana_api

    if ventana_api is not None:

        try:

            if (
                ventana_api
                .winfo_exists()
            ):

                ventana_api.lift()

                return

        except Exception:

            pass

    ventana_api = (
        tk.Toplevel(
            root
        )
    )

    ventana_api.title(
        "MasterX - Gemini"
    )

    ventana_api.geometry(
        "470x375"
    )

    ventana_api.resizable(
        False,
        False
    )

    ventana_api.attributes(
        "-topmost",
        True
    )

    ventana_api.configure(bg=MASTERX_BG)

    # =====================================================
    # CIERRE
    # =====================================================

    def cerrar_api():

        global ventana_api

        if obligatoria:

            respuesta = (
                messagebox.askyesno(

                    "MasterX",

                    (
                        "Gemini todavía no está configurado.\n\n"
                        "¿Quieres cerrar MasterX?"
                    ),

                    parent=
                        ventana_api
                )
            )

            if respuesta:

                ventana_api.destroy()

                ventana_api = None

                cerrar_masterx()

            return

        ventana_api.destroy()

        ventana_api = None

    ventana_api.protocol(
        "WM_DELETE_WINDOW",
        cerrar_api
    )

    marco = ttk.Frame(
        ventana_api,
        padding=22
    )

    marco.pack(
        fill="both",
        expand=True
    )

    ttk.Label(

        marco,

        text="Configurar Gemini",

        font=(
            "Segoe UI",
            17,
            "bold"
        )

    ).pack(
        pady=(0, 5)
    )

    ttk.Label(

        marco,

        text=(
            "Introduce tu API key de Google Gemini.\n"
            "MasterX la guardará mediante el almacén "
            "de credenciales del sistema."
        ),

        justify="center"

    ).pack(
        pady=(0, 15)
    )

    boton_google = ttk.Button(
        marco,
        text="Obtener API de Google",
        command=abrir_pagina_api_google
    )

    boton_google.pack(
        pady=(0, 14)
    )

    # =====================================================
    # API KEY
    # =====================================================

    variable_api = (
        tk.StringVar()
    )

    entrada = ttk.Entry(

        marco,

        textvariable=
            variable_api,

        show="•",

        width=50
    )

    entrada.pack(
        pady=(0, 8)
    )

    entrada.focus_set()

    mostrar_variable = (
        tk.BooleanVar(
            value=False
        )
    )

    def cambiar_visibilidad():

        if mostrar_variable.get():

            entrada.config(
                show=""
            )

        else:

            entrada.config(
                show="•"
            )

    ttk.Checkbutton(

        marco,

        text="Mostrar API key",

        variable=
            mostrar_variable,

        command=
            cambiar_visibilidad

    ).pack(
        pady=(0, 12)
    )

    estado = ttk.Label(

        marco,

        text=
            texto_estado_gemini(),

        font=(
            "Segoe UI",
            9,
            "bold"
        )
    )

    estado.pack(
        pady=(0, 10)
    )

    # =====================================================
    # PROBAR Y GUARDAR
    # =====================================================

    def ejecutar_guardado():

        clave = (
            variable_api
            .get()
            .strip()
        )

        if not clave:

            messagebox.showerror(

                "MasterX",

                "Introduce una API key.",

                parent=
                    ventana_api
            )

            return

        estado.config(
            text=
                "Probando conexión..."
        )

        ventana_api.update_idletasks()

        def tarea():

            correcto, detalle = (
                probar_api_key(
                    clave
                )
            )

            root.after(
                0,

                lambda:
                    finalizar_prueba(
                        correcto,
                        detalle,
                        clave
                    )
            )

        threading.Thread(
            target=tarea,
            daemon=True
        ).start()

    def finalizar_prueba(
        correcto,
        detalle,
        clave
    ):

        if not correcto:

            estado.config(
                text=
                    "Conexión fallida"
            )

            messagebox.showerror(

                "Gemini",

                (
                    "No pude validar la API key.\n\n"
                    + detalle
                ),

                parent=
                    ventana_api
            )

            return

        # -----------------------------------------
        # Guardar en keyring
        # -----------------------------------------

        if not guardar_api_key(
            clave
        ):

            estado.config(
                text=
                    "No pude guardar la API key."
            )

            messagebox.showerror(

                "MasterX",

                (
                    "La conexión funcionó, "
                    "pero no pude guardar la API key."
                ),

                parent=
                    ventana_api
            )

            return

        # -----------------------------------------
        # Inicializar cliente definitivo
        # -----------------------------------------

        if not inicializar_gemini():

            estado.config(
                text=
                    "Error inicializando Gemini."
            )

            return

        estado.config(
            text=
                "Gemini: Conectado ✓"
        )

        messagebox.showinfo(

            "MasterX",

            (
                "Gemini quedó configurado "
                "correctamente."
            ),

            parent=
                ventana_api
        )

        cerrar_api()

    # =====================================================
    # BOTONES
    # =====================================================

    botones = ttk.Frame(
        marco
    )

    botones.pack(
        fill="x",
        pady=(5, 0)
    )

    ttk.Button(

        botones,

        text=
            "Probar y guardar",

        command=
            ejecutar_guardado

    ).pack(
        side="right"
    )

    if not obligatoria:

        ttk.Button(

            botones,

            text="Cerrar",

            command=
                cerrar_api

        ).pack(
            side="right",
            padx=8
        )

    else:

        ttk.Button(

            botones,

            text="Salir",

            command=
                cerrar_api

        ).pack(
            side="left"
        )


# =========================================================
# OPENAI - PÁGINA DE API
# =========================================================

def abrir_pagina_api_openai():
    try:
        webbrowser.open(
            "https://platform.openai.com/api-keys"
        )
    except Exception as e:
        messagebox.showerror(
            "MasterX",
            "No pude abrir el navegador.\n\n" + str(e)
        )


# =========================================================
# VENTANA CONFIGURAR OPENAI
# =========================================================

def abrir_configuracion_openai(
    event=None,
    obligatoria=False
):

    global ventana_openai

    if ventana_openai is not None:
        try:
            if ventana_openai.winfo_exists():
                ventana_openai.lift()
                return
        except Exception:
            pass

    ventana_openai = tk.Toplevel(root)
    ventana_openai.title("MasterX - OpenAI")
    ventana_openai.geometry("480x385")
    ventana_openai.resizable(False, False)
    ventana_openai.attributes("-topmost", True)
    colorear_barra_titulo(
        ventana_openai,
        fondo="#0D0B18",
        texto="#EAF9FF",
        borde="#45D4FF"
    )

    def cerrar_openai():
        global ventana_openai

        if obligatoria and openai_client is None:
            respuesta = messagebox.askyesno(
                "MasterX",
                "OpenAI todavía no está configurado.\n\n¿Quieres cerrar MasterX?",
                parent=ventana_openai
            )
            if respuesta:
                ventana_openai.destroy()
                ventana_openai = None
                cerrar_masterx()
            return

        ventana_openai.destroy()
        ventana_openai = None

    ventana_openai.protocol(
        "WM_DELETE_WINDOW",
        cerrar_openai
    )

    marco = ttk.Frame(
        ventana_openai,
        padding=22
    )
    marco.pack(fill="both", expand=True)

    ttk.Label(
        marco,
        text="Configurar OpenAI",
        font=("Segoe UI", 17, "bold")
    ).pack(pady=(0, 5))

    ttk.Label(
        marco,
        text=(
            "Usa una API key de OpenAI. No es el inicio de sesión de ChatGPT.\n"
            "La clave se guardará en el almacén de credenciales del sistema."
        ),
        justify="center"
    ).pack(pady=(0, 12))

    ttk.Button(
        marco,
        text="Obtener API de OpenAI",
        command=abrir_pagina_api_openai
    ).pack(pady=(0, 14))

    variable_api = tk.StringVar()

    entrada = ttk.Entry(
        marco,
        textvariable=variable_api,
        show="•",
        width=50
    )
    entrada.pack(pady=(0, 8))
    entrada.focus_set()

    mostrar_variable = tk.BooleanVar(value=False)

    def cambiar_visibilidad():
        entrada.config(
            show="" if mostrar_variable.get() else "•"
        )

    ttk.Checkbutton(
        marco,
        text="Mostrar API key",
        variable=mostrar_variable,
        command=cambiar_visibilidad
    ).pack(pady=(0, 10))

    estado = ttk.Label(
        marco,
        text=texto_estado_openai(),
        font=("Segoe UI", 9, "bold")
    )
    estado.pack(pady=(0, 10))

    def finalizar_prueba(correcto, detalle, clave):
        if not correcto:
            codigo = "OTRO"
            mensaje = detalle

            if "|" in detalle:
                codigo, mensaje = detalle.split("|", 1)

            if codigo == "SIN_CUOTA":
                # La clave llegó correctamente a OpenAI, pero el proyecto
                # no tiene cuota/crédito. La guardamos para no obligar al
                # usuario a pegarla otra vez cuando agregue saldo.
                guardar_api_key_openai(clave)
                inicializar_openai()

                estado.config(text="API válida · Sin cuota/crédito")

                usar_gemini = messagebox.askyesno(
                    "OpenAI - Sin cuota",
                    mensaje +
                    "\n\nLa clave se guardó correctamente."
                    "\n\n¿Quieres usar Gemini por ahora?",
                    parent=ventana_openai
                )

                if usar_gemini:
                    global PROVEEDOR_IA
                    PROVEEDOR_IA = "gemini"
                    guardar_estado()
                    cerrar_openai()

                return

            estado.config(text="Conexión fallida")
            messagebox.showerror(
                "OpenAI",
                mensaje,
                parent=ventana_openai
            )
            return

        if not guardar_api_key_openai(clave):
            estado.config(text="No pude guardar la API key.")
            return

        if not inicializar_openai():
            estado.config(text="Error inicializando OpenAI.")
            return

        estado.config(text="OpenAI: Conectado ✓")
        messagebox.showinfo(
            "MasterX",
            "OpenAI quedó configurado correctamente.",
            parent=ventana_openai
        )
        cerrar_openai()

    def ejecutar_guardado():
        clave = variable_api.get().strip()
        if not clave:
            messagebox.showerror(
                "MasterX",
                "Introduce una API key.",
                parent=ventana_openai
            )
            return

        estado.config(text="Probando conexión...")
        ventana_openai.update_idletasks()

        def tarea():
            correcto, detalle = probar_api_key_openai(clave)
            root.after(
                0,
                lambda: finalizar_prueba(
                    correcto,
                    detalle,
                    clave
                )
            )

        threading.Thread(
            target=tarea,
            daemon=True
        ).start()

    botones = ttk.Frame(marco)
    botones.pack(fill="x", pady=(5, 0))

    ttk.Button(
        botones,
        text="Probar y guardar",
        command=ejecutar_guardado
    ).pack(side="right")

    if not obligatoria:
        ttk.Button(
            botones,
            text="Cerrar",
            command=cerrar_openai
        ).pack(side="right", padx=8)
    else:
        ttk.Button(
            botones,
            text="Salir",
            command=cerrar_openai
        ).pack(side="left")


# =========================================================
# SHORTCUT WRAPPERS
# =========================================================

def hotkey_automatico():

    root.after(
        0,
        analizar_zona_guardada
    )


def hotkey_manual():

    root.after(
        0,
        modo_manual
    )


def hotkey_marco():

    root.after(
        0,
        configurar_zona
    )


def hotkey_compacto():

    root.after(
        0,
        alternar_modo_compacto
    )


def hotkey_menu():

    root.after(
        0,
        abrir_menu_shortcuts
    )


def hotkey_historial():

    root.after(
        0,
        abrir_historial
    )


def hotkey_cerrar():

    # keyboard ejecuta los callbacks globales en otro hilo.
    # Tkinter debe cerrarse desde su hilo principal.
    root.after(
        0,
        cerrar_masterx
    )


# =========================================================
# REGISTRAR SHORTCUTS
# =========================================================

def _shortcut_mac_pynput(combinacion):
    """Convierte ctrl/alt/cmd/shift al formato de pynput GlobalHotKeys."""
    partes = [p.strip().lower() for p in combinacion.split("+") if p.strip()]
    mapa = {
        "ctrl": "<ctrl>", "control": "<ctrl>",
        "alt": "<alt>", "option": "<alt>", "opt": "<alt>",
        "shift": "<shift>",
        "cmd": "<cmd>", "command": "<cmd>", "meta": "<cmd>",
    }
    salida = []
    for parte in partes:
        salida.append(mapa.get(parte, parte))
    return "+".join(salida)


def registrar_shortcuts():
    global hotkeys_ids
    global mac_hotkeys_listener

    acciones = {
        "automatico": hotkey_automatico,
        "manual": hotkey_manual,
        "marco": hotkey_marco,
        "compacto": hotkey_compacto,
        "menu": hotkey_menu,
        "historial": hotkey_historial,
        "cerrar": hotkey_cerrar,
    }

    if ES_MAC:
        if mac_hotkeys_listener is not None:
            try:
                mac_hotkeys_listener.stop()
            except Exception:
                pass
            mac_hotkeys_listener = None

        if not PYNPUT_DISPONIBLE:
            print("macOS: falta pynput; los shortcuts globales están desactivados.")
            return

        mapa_hotkeys = {}
        for nombre, funcion in acciones.items():
            combinacion = shortcuts.get(nombre, "").strip().lower()
            if combinacion:
                try:
                    mapa_hotkeys[_shortcut_mac_pynput(combinacion)] = funcion
                except Exception as e:
                    print("Shortcut inválido:", nombre, e)

        try:
            mac_hotkeys_listener = pynput_keyboard.GlobalHotKeys(mapa_hotkeys)
            mac_hotkeys_listener.start()
            print("Shortcuts macOS registrados:", ", ".join(mapa_hotkeys.keys()))
        except Exception as e:
            print("No pude registrar shortcuts macOS:", e)
        return

    # Windows: conservar el backend original `keyboard`.
    for hotkey_id in list(hotkeys_ids.values()):
        try:
            keyboard.remove_hotkey(hotkey_id)
        except Exception:
            pass

    hotkeys_ids = {}
    for nombre, funcion in acciones.items():
        combinacion = shortcuts.get(nombre, "").strip().lower()
        if not combinacion:
            continue
        try:
            hotkey_id = keyboard.add_hotkey(combinacion, funcion)
            hotkeys_ids[nombre] = hotkey_id
            print(nombre, "=", combinacion)
        except Exception as e:
            print("Shortcut inválido:", nombre, e)


# =========================================================
# NORMALIZAR SHORTCUT
# =========================================================

def normalizar_shortcut(
    texto
):

    texto = (
        texto.strip()
        .lower()
        .replace(" ", "")
    )

    texto = texto.replace(
        "control",
        "ctrl"
    )

    while "++" in texto:

        texto = texto.replace(
            "++",
            "+"
        )

    return texto


# =========================================================
# MENÚ CONFIGURACIÓN
# =========================================================

# =========================================================
# BARRA DE TÍTULO WINDOWS - MASTERX
# =========================================================

def colorear_barra_titulo(
    ventana,
    fondo="#0D0B18",
    texto="#EAF9FF",
    borde="#45D4FF"
):

    """
    Colorea la barra nativa de Windows 10/11 usando DWM.
    Si Windows no soporta alguno de los atributos, simplemente
    continúa sin romper MasterX.
    """

    if os.name != "nt":
        return

    try:
        ventana.update_idletasks()

        hwnd = ctypes.windll.user32.GetParent(
            ventana.winfo_id()
        )

        def hex_a_colorref(hex_color):
            hex_color = hex_color.lstrip("#")
            r = int(hex_color[0:2], 16)
            g = int(hex_color[2:4], 16)
            b = int(hex_color[4:6], 16)

            # COLORREF usa formato 0x00BBGGRR
            return (
                r
                | (g << 8)
                | (b << 16)
            )

        atributos = (
            # DWMWA_BORDER_COLOR
            (34, hex_a_colorref(borde)),

            # DWMWA_CAPTION_COLOR
            (35, hex_a_colorref(fondo)),

            # DWMWA_TEXT_COLOR
            (36, hex_a_colorref(texto)),
        )

        for atributo, valor in atributos:

            dato = ctypes.c_int(
                valor
            )

            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd,
                atributo,
                ctypes.byref(dato),
                ctypes.sizeof(dato)
            )

    except Exception as e:

        print(
            "No pude colorear barra de título:",
            e
        )


def abrir_menu_shortcuts(
    event=None
):

    global ventana_shortcuts
    global OPACIDAD_COMPACTO
    global PROVEEDOR_IA
    global GEMINI_MODO

    if ventana_shortcuts is not None:
        try:
            if ventana_shortcuts.winfo_exists():
                ventana_shortcuts.lift()
                return
        except Exception:
            pass

    BG = "#0D0B18"
    PANEL = "#111A29"
    PANEL_2 = "#0B1422"
    CYAN = "#45D4FF"
    CYAN_DARK = "#087B9B"
    CYAN_DIM = "#174C60"
    ORANGE = "#FFA20A"
    WHITE = "#EAF9FF"
    MUTED = "#79A9B9"
    GREEN = "#2BE5A7"
    RED = "#FF4D6D"

    ventana_shortcuts = tk.Toplevel(root)
    ventana_shortcuts.title("MasterX - HUD Control")
    ventana_shortcuts.geometry("690x680")
    ventana_shortcuts.minsize(690, 640)
    ventana_shortcuts.attributes("-topmost", True)
    ventana_shortcuts.configure(bg=CYAN)

    # Barra superior nativa de Windows con el mismo tema MasterX.
    colorear_barra_titulo(
        ventana_shortcuts,
        fondo=BG,
        texto=WHITE,
        borde=CYAN
    )

    shell = tk.Frame(
        ventana_shortcuts,
        bg=BG,
        highlightthickness=2,
        highlightbackground=CYAN
    )
    shell.pack(
        fill="both",
        expand=True,
        padx=3,
        pady=3
    )

    # =====================================================
    # CABECERA HUD MÁS COMPACTA
    # =====================================================

    header = tk.Canvas(
        shell,
        height=165,
        bg=BG,
        highlightthickness=0
    )
    header.pack(fill="x")

    def dibujar_header(event=None):
        import math

        header.delete("all")
        w = max(header.winfo_width(), 660)

        header.create_line(22, 24, 160, 24, fill=CYAN, width=2)
        header.create_line(22, 24, 22, 60, fill=CYAN, width=2)
        header.create_line(w - 160, 24, w - 22, 24, fill=CYAN, width=2)
        header.create_line(w - 22, 24, w - 22, 60, fill=CYAN, width=2)

        cx, cy = w // 2, 82

        header.create_oval(cx-54, cy-54, cx+54, cy+54, outline=CYAN_DIM, width=2)
        header.create_arc(
            cx-49, cy-49, cx+49, cy+49,
            start=15,
            extent=130,
            style="arc",
            outline=CYAN,
            width=6
        )
        header.create_arc(
            cx-49, cy-49, cx+49, cy+49,
            start=165,
            extent=88,
            style="arc",
            outline=CYAN_DARK,
            width=6
        )
        header.create_arc(
            cx-41, cy-41, cx+41, cy+41,
            start=285,
            extent=50,
            style="arc",
            outline=ORANGE,
            width=4
        )

        for ang in range(0, 360, 45):
            a = math.radians(ang)
            x1 = cx + math.cos(a) * 58
            y1 = cy + math.sin(a) * 58
            x2 = cx + math.cos(a) * 64
            y2 = cy + math.sin(a) * 64
            header.create_line(x1, y1, x2, y2, fill=CYAN_DARK, width=1)

        header.create_text(
            cx, cy-5,
            text="MASTERX",
            fill=WHITE,
            font=("Segoe UI", 17, "bold")
        )
        header.create_text(
            cx, cy+17,
            text=f"SYSTEM CONTROL  //  v{MASTERX_VERSION}",
            fill=CYAN,
            font=("Consolas", 7, "bold")
        )

        estado = "ONLINE" if licencia_activa else "LOCKED"
        color_estado = GREEN if licencia_activa else RED

        header.create_text(
            46, 90,
            text="LICENSE",
            anchor="w",
            fill=MUTED,
            font=("Consolas", 7, "bold")
        )
        header.create_text(
            46, 109,
            text=f"● {estado}",
            anchor="w",
            fill=color_estado,
            font=("Consolas", 10, "bold")
        )

        header.create_text(
            w-46, 90,
            text="AI CORE",
            anchor="e",
            fill=MUTED,
            font=("Consolas", 7, "bold")
        )
        header.create_text(
            w-46, 109,
            text=nombre_proveedor_actual().upper(),
            anchor="e",
            fill=CYAN,
            font=("Consolas", 10, "bold")
        )

    header.bind("<Configure>", dibujar_header)

    # =====================================================
    # TABS
    # =====================================================

    barra_tabs = tk.Frame(shell, bg=BG)
    barra_tabs.pack(fill="x", padx=18, pady=(0, 8))

    contenedor = tk.Frame(shell, bg=BG)
    contenedor.pack(fill="both", expand=True, padx=18, pady=(0, 12))

    tab_general = tk.Frame(contenedor, bg=BG)
    tab_shortcuts = tk.Frame(contenedor, bg=BG)
    tab_diagnostico = tk.Frame(contenedor, bg=BG)

    diagnostico_desbloqueado = False
    PASSWORD_DIAGNOSTICO_SHA256 = "2e0e00cf30896b3b88120111d7cb724949caff3a95c167d7edc3a4203082ac9a"

    def validar_acceso_diagnostico():
        nonlocal diagnostico_desbloqueado
        if diagnostico_desbloqueado:
            return True

        clave = simpledialog.askstring(
            "MasterX - Diagnóstico local",
            "Contraseña de acceso:",
            show="*",
            parent=ventana_shortcuts
        )
        if clave is None:
            return False

        if hashlib.sha256(clave.encode("utf-8")).hexdigest() != PASSWORD_DIAGNOSTICO_SHA256:
            messagebox.showerror(
                "Acceso denegado",
                "Contraseña incorrecta.",
                parent=ventana_shortcuts
            )
            return False

        diagnostico_desbloqueado = True
        return True

    def mostrar_tab(nombre):
        if nombre == "diagnostico" and not validar_acceso_diagnostico():
            return

        tab_general.pack_forget()
        tab_shortcuts.pack_forget()
        tab_diagnostico.pack_forget()

        boton_tab_general.config(bg=PANEL_2, fg=MUTED)
        boton_tab_shortcuts.config(bg=PANEL_2, fg=MUTED)
        boton_tab_diagnostico.config(bg=PANEL_2, fg=MUTED)

        if nombre == "shortcuts":
            tab_shortcuts.pack(fill="both", expand=True)
            boton_tab_shortcuts.config(bg=CYAN_DARK, fg=WHITE)
        elif nombre == "diagnostico":
            tab_diagnostico.pack(fill="both", expand=True)
            boton_tab_diagnostico.config(bg=CYAN_DARK, fg=WHITE)
            ejecutar_diagnostico_local()
        else:
            tab_general.pack(fill="both", expand=True)
            boton_tab_general.config(bg=CYAN_DARK, fg=WHITE)

    boton_tab_general = tk.Button(
        barra_tabs,
        text="SISTEMA",
        command=lambda: mostrar_tab("general"),
        bg=CYAN_DARK,
        fg=WHITE,
        activebackground=CYAN,
        activeforeground=BG,
        relief="flat",
        borderwidth=0,
        cursor="hand2",
        font=("Consolas", 9, "bold"),
        padx=18,
        pady=7
    )
    boton_tab_general.pack(side="left")

    boton_tab_shortcuts = tk.Button(
        barra_tabs,
        text="SHORTCUTS",
        command=lambda: mostrar_tab("shortcuts"),
        bg=PANEL_2,
        fg=MUTED,
        activebackground=CYAN,
        activeforeground=BG,
        relief="flat",
        borderwidth=0,
        cursor="hand2",
        font=("Consolas", 9, "bold"),
        padx=18,
        pady=7
    )
    boton_tab_shortcuts.pack(side="left", padx=6)

    boton_tab_diagnostico = tk.Button(
        barra_tabs,
        text="DIAGNÓSTICO",
        command=lambda: mostrar_tab("diagnostico"),
        bg=PANEL_2,
        fg=MUTED,
        activebackground=CYAN,
        activeforeground=BG,
        relief="flat",
        borderwidth=0,
        cursor="hand2",
        font=("Consolas", 9, "bold"),
        padx=18,
        pady=7
    )
    boton_tab_diagnostico.pack(side="left")

    # =====================================================
    # HELPERS
    # =====================================================

    def crear_panel(padre, titulo, subtitulo=""):
        exterior = tk.Frame(padre, bg=CYAN_DIM)
        interior = tk.Frame(exterior, bg=PANEL)
        interior.pack(fill="both", expand=True, padx=1, pady=1)

        barra = tk.Frame(interior, bg=PANEL_2, height=28)
        barra.pack(fill="x")
        barra.pack_propagate(False)

        tk.Label(
            barra,
            text=f"  ◈  {titulo.upper()}",
            bg=PANEL_2,
            fg=CYAN,
            font=("Consolas", 8, "bold")
        ).pack(side="left", pady=5)

        if subtitulo:
            tk.Label(
                barra,
                text=subtitulo,
                bg=PANEL_2,
                fg=MUTED,
                font=("Consolas", 7)
            ).pack(side="right", padx=10)

        return exterior, interior

    def crear_boton(padre, texto, comando, accent=False):
        normal = ORANGE if accent else "#103C54"
        hover = "#FFC04A" if accent else CYAN_DARK
        fg = BG if accent else WHITE

        b = tk.Button(
            padre,
            text=texto,
            command=comando,
            bg=normal,
            fg=fg,
            activebackground=hover,
            activeforeground=fg,
            relief="flat",
            borderwidth=0,
            cursor="hand2",
            font=("Segoe UI", 8, "bold"),
            padx=10,
            pady=5
        )
        b.bind("<Enter>", lambda e: b.config(bg=hover))
        b.bind("<Leave>", lambda e: b.config(bg=normal))
        return b

    def hud_label(padre, texto, color=WHITE, bold=False):
        return tk.Label(
            padre,
            text=texto,
            bg=PANEL,
            fg=color,
            font=("Segoe UI", 8, "bold" if bold else "normal")
        )

    # =====================================================
    # TAB SISTEMA
    # =====================================================

    p_status, status = crear_panel(
        tab_general,
        "System Status",
        "MASTERX CORE"
    )
    p_status.pack(fill="x", pady=(0, 10))

    fila = tk.Frame(status, bg=PANEL)
    fila.pack(fill="x", padx=14, pady=11)

    licencia_txt = (
        f"{texto_estado_licencia()}  {licencia_mostrada()}"
        if licencia_activa else
        "LICENCIA NO ACTIVADA"
    )

    hud_label(
        fila,
        "● " + licencia_txt,
        GREEN if licencia_activa else RED,
        True
    ).pack(side="left")

    crear_boton(
        fila,
        "LICENCIA",
        lambda: abrir_configuracion_licencia(obligatoria=False)
    ).pack(side="right")

    # IA
    p_ia, ia = crear_panel(
        tab_general,
        "AI Core",
        "SELECT ENGINE"
    )
    p_ia.pack(fill="x", pady=(0, 10))

    variable_proveedor = tk.StringVar(value=PROVEEDOR_IA)

    estado_actual = hud_label(
        ia,
        f"NÚCLEO ACTIVO: {nombre_proveedor_actual().upper()}",
        CYAN,
        True
    )
    estado_actual.pack(anchor="w", padx=14, pady=(10, 4))

    def cambiar_proveedor():
        global PROVEEDOR_IA

        nuevo = variable_proveedor.get().strip().lower()

        if nuevo not in ("gemini", "openai"):
            nuevo = "gemini"

        PROVEEDOR_IA = nuevo
        guardar_estado()

        estado_actual.config(
            text=f"NÚCLEO ACTIVO: {nombre_proveedor_actual().upper()}"
        )

        dibujar_header()

    fila_g = tk.Frame(ia, bg=PANEL)
    fila_g.pack(fill="x", padx=14, pady=4)

    tk.Radiobutton(
        fila_g,
        text="GEMINI",
        variable=variable_proveedor,
        value="gemini",
        command=cambiar_proveedor,
        bg=PANEL,
        fg=WHITE,
        selectcolor=PANEL_2,
        activebackground=PANEL,
        activeforeground=CYAN,
        font=("Segoe UI", 8, "bold")
    ).pack(side="left")

    hud_label(
        fila_g,
        "● READY" if gemini_client is not None else "○ OFFLINE",
        GREEN if gemini_client is not None else MUTED,
        True
    ).pack(side="left", padx=7)

    crear_boton(
        fila_g,
        "CONFIG",
        lambda: abrir_configuracion_api(obligatoria=False)
    ).pack(side="right")

    crear_boton(
        fila_g,
        "API GOOGLE",
        abrir_pagina_api_google
    ).pack(side="right", padx=5)

    fila_modo = tk.Frame(ia, bg=PANEL)
    fila_modo.pack(fill="x", padx=34, pady=(0, 5))

    variable_modo_gemini = tk.StringVar(value=GEMINI_MODO)

    etiqueta_modelo = hud_label(
        fila_modo,
        "FLASH-LITE / FAST"
        if GEMINI_MODO == "rapido"
        else "FLASH / PRECISE",
        CYAN
    )
    etiqueta_modelo.pack(side="right")

    def cambiar_modo_gemini():
        global GEMINI_MODO

        nuevo = variable_modo_gemini.get().strip().lower()

        GEMINI_MODO = (
            nuevo
            if nuevo in ("rapido", "preciso")
            else "rapido"
        )

        guardar_estado()

        etiqueta_modelo.config(
            text=(
                "FLASH-LITE / FAST"
                if GEMINI_MODO == "rapido"
                else "FLASH / PRECISE"
            )
        )

    for txt, val in (
        ("Rápido", "rapido"),
        ("Preciso", "preciso")
    ):
        tk.Radiobutton(
            fila_modo,
            text=txt,
            variable=variable_modo_gemini,
            value=val,
            command=cambiar_modo_gemini,
            bg=PANEL,
            fg=WHITE,
            selectcolor=PANEL_2,
            activebackground=PANEL,
            activeforeground=CYAN,
            font=("Segoe UI", 8)
        ).pack(side="left", padx=(0, 8))

    fila_o = tk.Frame(ia, bg=PANEL)
    fila_o.pack(fill="x", padx=14, pady=(3, 10))

    tk.Radiobutton(
        fila_o,
        text="OPENAI / GPT",
        variable=variable_proveedor,
        value="openai",
        command=cambiar_proveedor,
        bg=PANEL,
        fg=WHITE,
        selectcolor=PANEL_2,
        activebackground=PANEL,
        activeforeground=CYAN,
        font=("Segoe UI", 8, "bold")
    ).pack(side="left")

    hud_label(
        fila_o,
        "● READY" if openai_client is not None else "○ OFFLINE",
        GREEN if openai_client is not None else MUTED,
        True
    ).pack(side="left", padx=7)

    crear_boton(
        fila_o,
        "CONFIG",
        lambda: abrir_configuracion_openai(obligatoria=False)
    ).pack(side="right")

    crear_boton(
        fila_o,
        "API OPENAI",
        abrir_pagina_api_openai
    ).pack(side="right", padx=5)

    # Opacidad
    p_op, op = crear_panel(
        tab_general,
        "Compact Mode",
        "VISIBILITY"
    )
    p_op.pack(fill="x", pady=(0, 10))

    fila_op = tk.Frame(op, bg=PANEL)
    fila_op.pack(fill="x", padx=14, pady=10)

    variable_opacidad = tk.IntVar(
        value=int(OPACIDAD_COMPACTO * 100)
    )

    valor_alpha = hud_label(
        fila_op,
        f"{variable_opacidad.get()}%",
        CYAN,
        True
    )
    valor_alpha.pack(side="right")

    hud_label(
        fila_op,
        "OPACIDAD",
        MUTED,
        True
    ).pack(side="left")

    def cambiar_opacidad(valor):
        global OPACIDAD_COMPACTO

        porcentaje = int(float(valor))
        variable_opacidad.set(porcentaje)
        OPACIDAD_COMPACTO = porcentaje / 100.0

        valor_alpha.config(
            text=f"{porcentaje}%"
        )

        if modo_compacto:
            root.attributes(
                "-alpha",
                OPACIDAD_COMPACTO
            )

    escala = tk.Scale(
        fila_op,
        from_=10,
        to=100,
        orient="horizontal",
        variable=variable_opacidad,
        command=cambiar_opacidad,
        showvalue=False,
        length=360,
        bg=PANEL,
        fg=WHITE,
        troughcolor=PANEL_2,
        activebackground=CYAN,
        highlightthickness=0,
        bd=0
    )
    escala.pack(side="left", fill="x", expand=True, padx=12)

    # =====================================================
    # ACTUALIZACIONES
    # =====================================================

    p_update, update_panel = crear_panel(
        tab_general,
        "MasterX Update",
        "BETA CHANNEL"
    )
    p_update.pack(
        fill="x",
        pady=(0, 10)
    )

    fila_update = tk.Frame(
        update_panel,
        bg=PANEL
    )
    fila_update.pack(
        fill="x",
        padx=14,
        pady=10
    )

    estado_update_label = hud_label(
        fila_update,
        texto_estado_actualizacion(),
        MUTED,
        True
    )
    estado_update_label.pack(
        side="left"
    )

    version_update_label = hud_label(
        fila_update,
        f"LOCAL {MASTERX_VERSION}",
        CYAN
    )
    version_update_label.pack(
        side="left",
        padx=12
    )

    def refrescar_estado_update(
        resultado
    ):

        codigo = resultado.get(
            "estado",
            ""
        )

        if codigo == "disponible":
            color = ORANGE

            version_update_label.config(
                text=(
                    "REMOTA "
                    + resultado.get(
                        "version_remota",
                        "?"
                    )
                )
            )

        elif codigo == "actualizado":
            color = GREEN

            version_update_label.config(
                text=(
                    "LOCAL "
                    + MASTERX_VERSION
                )
            )

        elif codigo == "local_superior":
            color = CYAN

            version_update_label.config(
                text=(
                    "REMOTA "
                    + resultado.get(
                        "version_remota",
                        "?"
                    )
                )
            )

        elif codigo == "error":
            color = RED

            version_update_label.config(
                text="REVISA INTERNET"
            )

        else:
            color = MUTED

        estado_update_label.config(
            text=texto_estado_actualizacion(
                resultado
            ),
            fg=color
        )

    def buscar_actualizaciones_manual():

        global estado_actualizacion

        estado_actualizacion = {
            **estado_actualizacion,
            "estado": "comprobando",
        }

        estado_update_label.config(
            text="◌ COMPROBANDO...",
            fg=CYAN
        )

        version_update_label.config(
            text=f"LOCAL {MASTERX_VERSION}"
        )

        def tarea():

            resultado = (
                consultar_manifest_actualizaciones()
            )

            def terminar():

                refrescar_estado_update(
                    resultado
                )

                if (
                    resultado.get("estado")
                    == "disponible"
                ):

                    confirmar = messagebox.askyesno(
                        "MasterX - Update",
                        (
                            "Actualización disponible.\n\n"
                            f"Instalada: {MASTERX_VERSION}\n"
                            f"Nueva: {resultado.get('version_remota')}\n\n"
                            f"{resultado.get('notes', '')}\n\n"
                            "¿Quieres descargar y verificar la actualización ahora?"
                        ),
                        parent=ventana_shortcuts
                    )

                    if confirmar:
                        estado_update_label.config(text="↓ DESCARGANDO...", fg=CYAN)

                        def descargar_en_hilo():
                            try:
                                def progreso(descargado, total):
                                    if total > 0:
                                        porcentaje = int(descargado * 100 / total)
                                        root.after(0, lambda p=porcentaje: estado_update_label.config(text=f"↓ DESCARGANDO {p}%", fg=CYAN))

                                destino, sha_real = descargar_actualizacion(resultado, progreso)

                                def descarga_ok():
                                    estado_update_label.config(text="✓ UPDATE VERIFICADO", fg=GREEN)
                                    messagebox.showinfo(
                                        "MasterX - Update",
                                        "UPDATE VERIFICADO ✓\n\n"
                                        f"Archivo: {os.path.basename(destino)}\n\n"
                                        f"SHA-256:\n{sha_real}\n\n"
                                        "La actualización fue descargada correctamente. "
                                        "Esta beta todavía NO reemplaza automáticamente el EXE actual.",
                                        parent=ventana_shortcuts
                                    )
                                    try:
                                        abrir_carpeta_sistema(os.path.dirname(destino))
                                    except Exception:
                                        pass

                                root.after(0, descarga_ok)

                            except Exception as e:
                                def descarga_error(error=str(e)):
                                    estado_update_label.config(text="× ERROR DE DESCARGA", fg=RED)
                                    messagebox.showerror(
                                        "MasterX - Update",
                                        "No pude descargar/verificar la actualización.\n\n" + error,
                                        parent=ventana_shortcuts
                                    )
                                root.after(0, descarga_error)

                        threading.Thread(target=descargar_en_hilo, daemon=True).start()

                elif (
                    resultado.get("estado")
                    == "actualizado"
                ):

                    messagebox.showinfo(
                        "MasterX - Update",
                        (
                            "MasterX está actualizado.\n\n"
                            f"Versión instalada: {MASTERX_VERSION}\n"
                            f"Última versión publicada: {resultado.get('version_remota', MASTERX_VERSION)}"
                        ),
                        parent=ventana_shortcuts
                    )

                elif (
                    resultado.get("estado")
                    == "local_superior"
                ):

                    messagebox.showinfo(
                        "MasterX - Update",
                        (
                            "Estás utilizando una compilación más reciente que la versión pública.\n\n"
                            f"Versión instalada: {MASTERX_VERSION}\n"
                            f"Última versión publicada: {resultado.get('version_remota', '?')}\n\n"
                            "No es necesario actualizar."
                        ),
                        parent=ventana_shortcuts
                    )

                else:

                    messagebox.showwarning(
                        "MasterX - Update",
                        (
                            "No pude comprobar actualizaciones.\n\n"
                            + resultado.get(
                                "error",
                                "Error desconocido."
                            )
                        ),
                        parent=ventana_shortcuts
                    )

            root.after(
                0,
                terminar
            )

        threading.Thread(
            target=tarea,
            daemon=True
        ).start()

    crear_boton(
        fila_update,
        "BUSCAR UPDATE",
        buscar_actualizaciones_manual
    ).pack(
        side="right"
    )

    # Si la comprobación automática ya terminó antes de abrir el menú,
    # reflejamos el resultado.
    refrescar_estado_update(
        estado_actualizacion
    )

    # Botones del sistema
    acciones = tk.Frame(tab_general, bg=BG)
    acciones.pack(fill="x", pady=(4, 0))

    crear_boton(
        acciones,
        "HISTORIAL",
        abrir_historial
    ).pack(side="left")

    crear_boton(
        acciones,
        "SHORTCUTS",
        lambda: mostrar_tab("shortcuts")
    ).pack(side="left", padx=6)

    crear_boton(
        acciones,
        "CERRAR MENÚ",
        ventana_shortcuts.destroy
    ).pack(side="right")

    crear_boton(
        acciones,
        "SALIR MASTERX",
        lambda: (
            cerrar_masterx()
            if messagebox.askyesno(
                "MasterX",
                "¿Cerrar MasterX completamente?",
                parent=ventana_shortcuts
            )
            else None
        ),
        accent=True
    ).pack(side="right", padx=6)

    # =====================================================
    # TAB DIAGNÓSTICO LOCAL
    # =====================================================

    diagnostico_header = tk.Frame(tab_diagnostico, bg=PANEL_2)
    diagnostico_header.pack(fill="x", pady=(0, 8))

    hud_label(
        diagnostico_header,
        "SELF-TEST LOCAL  //  NO ENVÍA DATOS",
        CYAN
    ).pack(side="left", padx=12, pady=8)

    diagnostico_texto = tk.Text(
        tab_diagnostico,
        bg=PANEL,
        fg=WHITE,
        insertbackground=CYAN,
        relief="flat",
        highlightthickness=1,
        highlightbackground=CYAN_DIM,
        font=("Consolas", 9),
        wrap="word"
    )
    diagnostico_texto.pack(fill="both", expand=True, pady=(0, 8))

    def _diag_linea(estado, nombre, detalle=""):
        prefijo = {
            "OK": "[OK]  ",
            "WARN": "[WARN]",
            "FAIL": "[FAIL]"
        }.get(estado, "[INFO]")
        texto = f"{prefijo} {nombre}"
        if detalle:
            texto += f" -> {detalle}"
        return texto

    def ejecutar_diagnostico_local():
        resultados = []

        def agregar(estado, nombre, detalle=""):
            resultados.append((estado, nombre, detalle))

        agregar("OK", "Sistema operativo", f"{platform.system()} {platform.machine()}")
        agregar("OK", "Python", platform.python_version())
        agregar("OK", "Versión MasterX", MASTERX_VERSION)

        try:
            agregar("OK" if os.path.isfile(RUTA_CONFIG) else "WARN", "Configuración local", RUTA_CONFIG)
        except Exception as e:
            agregar("FAIL", "Configuración local", str(e))

        try:
            agregar("OK" if os.path.isfile(RUTA_LOGO) else "FAIL", "Logo/recursos", RUTA_LOGO)
        except Exception as e:
            agregar("FAIL", "Logo/recursos", str(e))

        try:
            tess = getattr(pytesseract.pytesseract, "tesseract_cmd", "")
            tess_ok = bool(TESSERACT_OK and tess and os.path.exists(tess))
            agregar("OK" if tess_ok else "FAIL", "Tesseract OCR", tess or "no localizado")
        except Exception as e:
            agregar("FAIL", "Tesseract OCR", str(e))

        try:
            # Captura mínima: comprueba permiso/backend sin procesar contenido del usuario.
            captura = ImageGrab.grab(bbox=(0, 0, 2, 2))
            agregar("OK" if captura.size == (2, 2) else "WARN", "Captura de pantalla", str(captura.size))
        except Exception as e:
            agregar("FAIL", "Captura de pantalla", str(e))

        agregar("OK" if proveedor_configurado() else "WARN", "Proveedor IA", nombre_proveedor_actual())

        if ES_MAC:
            agregar("OK" if PYNPUT_DISPONIBLE else "FAIL", "Backend shortcuts macOS", "pynput")
        else:
            agregar("OK" if keyboard is not None else "FAIL", "Backend shortcuts Windows", "keyboard")

        agregar("OK" if PYSTRAY_DISPONIBLE else "WARN", "Bandeja / segundo plano", "pystray")
        agregar("OK" if DND_DISPONIBLE else "WARN", "Drag & Drop", "tkinterdnd2")
        agregar("OK" if licencia_activa else "WARN", "Licencia local", "activa" if licencia_activa else "inactiva")

        try:
            if ES_WINDOWS and win32gui is not None:
                hwnd = win32gui.GetForegroundWindow()
                agregar("OK" if hwnd else "WARN", "Ventana activa", str(hwnd))
            elif ES_MAC:
                agregar("WARN", "Ventana activa macOS", "fallback pendiente de Quartz/Accesibilidad")
            else:
                agregar("WARN", "Ventana activa", "backend no específico")
        except Exception as e:
            agregar("FAIL", "Ventana activa", str(e))

        try:
            estado_up = estado_actualizacion.get("estado", "sin comprobar") if isinstance(estado_actualizacion, dict) else "sin comprobar"
            agregar("OK" if estado_up not in ("error", "sin comprobar") else "WARN", "Updater", str(estado_up))
        except Exception as e:
            agregar("WARN", "Updater", str(e))

        ok = sum(1 for r in resultados if r[0] == "OK")
        warn = sum(1 for r in resultados if r[0] == "WARN")
        fail = sum(1 for r in resultados if r[0] == "FAIL")

        lineas = [
            "MASTERX DIAGNOSTIC // LOCAL ONLY",
            "=" * 48,
            *[_diag_linea(*r) for r in resultados],
            "",
            "=" * 48,
            f"RESULTADO: {ok} OK / {warn} WARN / {fail} FAIL",
            "Este informe permanece local y no se transmite automáticamente."
        ]

        diagnostico_texto.config(state="normal")
        diagnostico_texto.delete("1.0", "end")
        diagnostico_texto.insert("1.0", "\n".join(lineas))
        diagnostico_texto.config(state="disabled")

    diagnostico_footer = tk.Frame(tab_diagnostico, bg=BG)
    diagnostico_footer.pack(fill="x")

    crear_boton(
        diagnostico_footer,
        "VOLVER",
        lambda: mostrar_tab("general")
    ).pack(side="left")

    crear_boton(
        diagnostico_footer,
        "REPETIR SELF-TEST",
        ejecutar_diagnostico_local,
        accent=True
    ).pack(side="right")

    # =====================================================
    # TAB SHORTCUTS
    # =====================================================

    p_keys, keys = crear_panel(
        tab_shortcuts,
        "Command Matrix",
        "GLOBAL HOTKEYS"
    )
    p_keys.pack(fill="both", expand=True)

    campos = {}

    acciones_shortcuts = [
        ("automatico", "Analizar automático"),
        ("manual", "Selección manual"),
        ("marco", "Configurar marco"),
        ("compacto", "Modo compacto"),
        ("menu", "Abrir configuración"),
        ("historial", "Abrir historial"),
        ("cerrar", "Cerrar MasterX"),
    ]

    tabla = tk.Frame(keys, bg=PANEL)
    tabla.pack(fill="both", expand=True, padx=16, pady=14)
    tabla.columnconfigure(1, weight=1)
    tabla.columnconfigure(2, weight=0)

    for fila_n, (clave, etiqueta) in enumerate(acciones_shortcuts):

        hud_label(
            tabla,
            f"{fila_n+1:02d}  {etiqueta}",
            WHITE
        ).grid(
            row=fila_n,
            column=0,
            sticky="w",
            padx=(0, 14),
            pady=6
        )

        variable = tk.StringVar(
            value=shortcuts.get(clave, "")
        )

        entrada = tk.Entry(
            tabla,
            textvariable=variable,
            bg=PANEL_2,
            fg=CYAN,
            insertbackground=CYAN,
            selectbackground=CYAN_DARK,
            selectforeground=WHITE,
            relief="flat",
            highlightthickness=1,
            highlightbackground=CYAN_DIM,
            highlightcolor=CYAN,
            font=("Consolas", 9, "bold")
        )

        entrada.grid(
            row=fila_n,
            column=1,
            sticky="ew",
            pady=6,
            ipady=5
        )

        campos[clave] = variable

        def capturar_shortcut(clave_obj=clave, variable_obj=variable, entrada_obj=entrada):
            """Captura la siguiente combinación real de teclas sin escribirla a mano."""

            entrada_obj.config(state="normal")
            variable_obj.set("PRESIONA LA COMBINACIÓN...")
            entrada_obj.focus_set()

            def finalizar(valor):
                valor = normalizar_shortcut(valor)
                root.after(0, lambda: variable_obj.set(valor))
                root.after(0, lambda: entrada_obj.focus_set())

            def fallo(mensaje):
                root.after(0, lambda: variable_obj.set(shortcuts.get(clave_obj, "")))
                root.after(0, lambda: messagebox.showerror(
                    "Captura de shortcut",
                    mensaje,
                    parent=ventana_shortcuts
                ))

            if ES_WINDOWS:
                if keyboard is None:
                    fallo("El backend keyboard no está disponible.")
                    return

                def worker_windows():
                    try:
                        # read_hotkey espera una combinación completa y devuelve
                        # una cadena como ctrl+shift+a. suppress=False evita bloquear
                        # la tecla para el resto del sistema.
                        valor = keyboard.read_hotkey(suppress=False)
                        finalizar(valor)
                    except Exception as e:
                        fallo("No pude capturar la combinación:\n" + str(e))

                threading.Thread(target=worker_windows, daemon=True).start()
                return

            if ES_MAC:
                if not PYNPUT_DISPONIBLE:
                    fallo("pynput no está disponible en macOS.")
                    return

                modificadores = set()
                estado = {"principal": None, "listener": None}

                mapa_mod = {
                    pynput_keyboard.Key.ctrl: "ctrl",
                    pynput_keyboard.Key.ctrl_l: "ctrl",
                    pynput_keyboard.Key.ctrl_r: "ctrl",
                    pynput_keyboard.Key.alt: "option",
                    pynput_keyboard.Key.alt_l: "option",
                    pynput_keyboard.Key.alt_r: "option",
                    pynput_keyboard.Key.shift: "shift",
                    pynput_keyboard.Key.shift_l: "shift",
                    pynput_keyboard.Key.shift_r: "shift",
                    pynput_keyboard.Key.cmd: "cmd",
                    pynput_keyboard.Key.cmd_l: "cmd",
                    pynput_keyboard.Key.cmd_r: "cmd",
                }

                def nombre_tecla(key):
                    if key in mapa_mod:
                        return mapa_mod[key]
                    try:
                        if key.char:
                            return str(key.char).lower()
                    except Exception:
                        pass
                    nombre = getattr(key, "name", None)
                    if nombre:
                        return nombre.lower()
                    texto_key = str(key)
                    if texto_key.startswith("Key."):
                        return texto_key[4:].lower()
                    return texto_key.lower()

                def on_press(key):
                    nombre = nombre_tecla(key)
                    if nombre in {"ctrl", "option", "shift", "cmd"}:
                        modificadores.add(nombre)
                        return
                    if estado["principal"] is None:
                        estado["principal"] = nombre

                def on_release(key):
                    principal = estado["principal"]
                    if principal is None:
                        return

                    orden = ["ctrl", "option", "shift", "cmd"]
                    partes = [m for m in orden if m in modificadores]
                    partes.append(principal)
                    finalizar("+".join(partes))
                    return False

                try:
                    listener = pynput_keyboard.Listener(
                        on_press=on_press,
                        on_release=on_release
                    )
                    estado["listener"] = listener
                    listener.start()
                except Exception as e:
                    fallo("No pude iniciar la captura en macOS:\n" + str(e))
                return

            fallo("La captura automática todavía no está disponible en este sistema.")

        crear_boton(
            tabla,
            "CAPTURAR",
            capturar_shortcut
        ).grid(
            row=fila_n,
            column=2,
            padx=(8, 0),
            pady=6
        )

    def guardar_shortcuts_menu():

        nuevos = {}

        for clave, variable in campos.items():
            nuevos[clave] = normalizar_shortcut(
                variable.get()
            )

        usados = {}

        for clave, combinacion in nuevos.items():

            if not combinacion:
                continue

            if combinacion in usados:

                messagebox.showerror(
                    "Shortcut duplicado",
                    f"{combinacion} ya está utilizado.",
                    parent=ventana_shortcuts
                )

                return

            usados[combinacion] = clave

        for clave, combinacion in nuevos.items():

            if not combinacion:
                continue

            try:
                if ES_MAC:
                    if not PYNPUT_DISPONIBLE:
                        raise RuntimeError("pynput no está instalado")
                    # GlobalHotKeys valida el formato al construirse; no arrancamos
                    # un listener temporal para evitar pedir permisos innecesariamente.
                    convertido = _shortcut_mac_pynput(combinacion)
                    if not convertido:
                        raise ValueError("shortcut vacío")
                else:
                    prueba = keyboard.add_hotkey(
                        combinacion,
                        lambda: None
                    )
                    keyboard.remove_hotkey(prueba)

            except Exception:
                messagebox.showerror(
                    "Shortcut inválido",
                    "No pude interpretar:\n\n" + combinacion,
                    parent=ventana_shortcuts
                )
                return

        shortcuts.clear()
        shortcuts.update(nuevos)

        guardar_estado()
        registrar_shortcuts()

        messagebox.showinfo(
            "MasterX",
            "Shortcuts guardados.",
            parent=ventana_shortcuts
        )

    def restaurar_defaults():

        for clave, valor in SHORTCUTS_DEFAULT.items():

            if clave in campos:
                campos[clave].set(
                    valor
                )

    footer_keys = tk.Frame(tab_shortcuts, bg=BG)
    footer_keys.pack(fill="x", pady=(10, 0))

    crear_boton(
        footer_keys,
        "VOLVER",
        lambda: mostrar_tab("general")
    ).pack(side="left")

    crear_boton(
        footer_keys,
        "RESTAURAR",
        restaurar_defaults
    ).pack(side="left", padx=6)

    crear_boton(
        footer_keys,
        "GUARDAR SHORTCUTS",
        guardar_shortcuts_menu,
        accent=True
    ).pack(side="right")

    mostrar_tab("general")


# =========================================================
# SEGUNDO PLANO / BANDEJA
# =========================================================

def mostrar_masterx_desde_tray(icon=None, item=None):
    global masterx_en_segundo_plano
    masterx_en_segundo_plano = False

    def _mostrar():
        try:
            root.deiconify()
            root.attributes("-topmost", True)
            root.lift()
        except Exception:
            pass

    try:
        root.after(0, _mostrar)
    except Exception:
        pass


def ocultar_masterx_a_bandeja(event=None):
    """Oculta la interfaz sin terminar OCR, IA ni shortcuts globales."""
    global masterx_en_segundo_plano
    masterx_en_segundo_plano = True
    try:
        guardar_estado()
    except Exception:
        pass
    try:
        root.withdraw()
    except Exception:
        pass


def _crear_imagen_tray():
    try:
        ruta = resource_path("masterx.png")
        if os.path.isfile(ruta):
            return Image.open(ruta).convert("RGBA").resize((64, 64))
    except Exception:
        pass

    # Icono de respaldo generado en memoria; no depende de archivos externos.
    img = Image.new("RGBA", (64, 64), (5, 11, 24, 255))
    return img


def iniciar_bandeja():
    global tray_icon
    global tray_iniciado

    if tray_iniciado or not PYSTRAY_DISPONIBLE:
        if not PYSTRAY_DISPONIBLE:
            print("AVISO: instala pystray para habilitar la bandeja del sistema.")
        return

    try:
        menu = pystray.Menu(
            pystray.MenuItem("Abrir MasterX", mostrar_masterx_desde_tray, default=True),
            pystray.MenuItem("Ocultar", ocultar_masterx_a_bandeja),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Salir", lambda icon, item: root.after(0, cerrar_masterx)),
        )
        tray_icon = pystray.Icon("MasterX", _crear_imagen_tray(), "MasterX", menu)
        tray_iniciado = True

        # Windows funciona correctamente en hilo separado. En macOS run_detached
        # coopera mejor con el loop gráfico principal cuando está disponible.
        if ES_MAC and hasattr(tray_icon, "run_detached"):
            tray_icon.run_detached()
        else:
            threading.Thread(target=tray_icon.run, daemon=True).start()
    except Exception as e:
        tray_iniciado = False
        print("No pude iniciar la bandeja/menu bar:", e)


def cerrar_masterx(event=None):
    """Cierra MasterX completamente. La X normal debe usar ocultar_masterx_a_bandeja()."""
    global tray_icon
    global mac_hotkeys_listener

    try:
        guardar_estado()
    except Exception:
        pass

    if ES_MAC and mac_hotkeys_listener is not None:
        try:
            mac_hotkeys_listener.stop()
        except Exception:
            pass
        mac_hotkeys_listener = None
    else:
        try:
            keyboard.unhook_all_hotkeys()
        except Exception:
            pass
        try:
            keyboard.unhook_all()
        except Exception:
            pass

    if tray_icon is not None:
        try:
            tray_icon.stop()
        except Exception:
            pass
        tray_icon = None

    try:
        threading.Timer(0.35, lambda: os._exit(0)).start()
    except Exception:
        pass

    try:
        root.quit()
    except Exception:
        pass
    try:
        root.destroy()
    except Exception:
        pass


# =========================================================
# CARGAR CONFIG
# =========================================================

cargar_configuracion()


# =========================================================
# INICIALIZAR PROVEEDORES DE IA
# =========================================================

inicializar_gemini()
inicializar_openai()


# =========================================================
# INTERFAZ
# =========================================================

if DND_DISPONIBLE:
    root = TkinterDnD.Tk()
else:
    root = tk.Tk()
    print(
        "AVISO: tkinterdnd2 no está instalado. "
        "El arrastre de imágenes/texto estará desactivado."
    )

# =========================================================
# TEMA MASTERX BETA 2 - FUTURISTIC BLUE
# =========================================================

MASTERX_BG = "#050B18"
MASTERX_PANEL = "#08182D"
MASTERX_PANEL_2 = "#0B2340"
MASTERX_BORDER = "#007BFF"
MASTERX_PRIMARY = "#00A8FF"
MASTERX_NEON = "#00D9FF"
MASTERX_TEXT = "#F4FAFF"
MASTERX_TEXT_2 = "#9CC9E8"
MASTERX_SUCCESS = "#28E6A7"
MASTERX_ERROR = "#FF4D6D"

try:
    estilo_masterx = ttk.Style(root)

    # "clam" permite controlar mucho mejor los colores que el tema nativo.
    try:
        estilo_masterx.theme_use("clam")
    except Exception:
        pass

    estilo_masterx.configure(
        "TFrame",
        background=MASTERX_BG
    )

    estilo_masterx.configure(
        "TLabel",
        background=MASTERX_BG,
        foreground=MASTERX_TEXT,
        font=("Segoe UI", 9)
    )

    estilo_masterx.configure(
        "TLabelFrame",
        background=MASTERX_BG,
        foreground=MASTERX_PRIMARY,
        bordercolor=MASTERX_BORDER,
        relief="solid"
    )

    estilo_masterx.configure(
        "TLabelFrame.Label",
        background=MASTERX_BG,
        foreground=MASTERX_PRIMARY,
        font=("Segoe UI", 9, "bold")
    )

    estilo_masterx.configure(
        "TButton",
        background="#0066CC",
        foreground=MASTERX_TEXT,
        borderwidth=0,
        focusthickness=0,
        padding=(10, 6),
        font=("Segoe UI", 9, "bold")
    )

    estilo_masterx.map(
        "TButton",
        background=[
            ("active", MASTERX_PRIMARY),
            ("pressed", "#004C99")
        ],
        foreground=[
            ("active", "#FFFFFF"),
            ("pressed", "#FFFFFF")
        ]
    )

    estilo_masterx.configure(
        "TEntry",
        fieldbackground=MASTERX_PANEL_2,
        foreground=MASTERX_TEXT,
        insertcolor=MASTERX_NEON,
        bordercolor="#14476E",
        lightcolor="#14476E",
        darkcolor="#14476E",
        padding=5
    )

    estilo_masterx.map(
        "TEntry",
        bordercolor=[
            ("focus", MASTERX_NEON)
        ],
        lightcolor=[
            ("focus", MASTERX_NEON)
        ],
        darkcolor=[
            ("focus", MASTERX_NEON)
        ]
    )

    estilo_masterx.configure(
        "TCheckbutton",
        background=MASTERX_BG,
        foreground=MASTERX_TEXT,
        font=("Segoe UI", 9)
    )

    estilo_masterx.map(
        "TCheckbutton",
        background=[
            ("active", MASTERX_BG)
        ],
        foreground=[
            ("active", MASTERX_NEON)
        ]
    )

    estilo_masterx.configure(
        "TRadiobutton",
        background=MASTERX_BG,
        foreground=MASTERX_TEXT,
        font=("Segoe UI", 9)
    )

    estilo_masterx.map(
        "TRadiobutton",
        background=[
            ("active", MASTERX_BG)
        ],
        foreground=[
            ("active", MASTERX_NEON),
            ("selected", MASTERX_NEON)
        ]
    )

    estilo_masterx.configure(
        "Horizontal.TScale",
        background=MASTERX_BG,
        troughcolor=MASTERX_PANEL_2
    )

except Exception as e:
    print("Aviso tema visual:", e)


root.title(
    "MasterX"
)

root.overrideredirect(
    True
)

root.attributes(
    "-topmost",
    True
)

# Al cerrar/ocultar la interfaz, MasterX permanece disponible en la bandeja.
try:
    root.protocol("WM_DELETE_WINDOW", ocultar_masterx_a_bandeja)
except Exception:
    pass

root.geometry(

    f"{TAMANO_NORMAL}"
    f"x{TAMANO_NORMAL}"
    f"+{posicion_x}"
    f"+{posicion_y}"
)


# =========================================================
# LOGO
# =========================================================

if os.path.exists(
    RUTA_LOGO_EXTERNO
):

    RUTA_LOGO = (
        RUTA_LOGO_EXTERNO
    )

else:

    RUTA_LOGO = (
        ruta_recurso(
            "masterx.png"
        )
    )


if not os.path.exists(
    RUTA_LOGO
):

    raise FileNotFoundError(
        "No encontré masterx.png."
    )


imagen_original = (
    Image.open(
        RUTA_LOGO
    )
)

imagen_original = (
    imagen_original.resize(

        (
            TAMANO_NORMAL,
            TAMANO_NORMAL
        ),

        Image.Resampling.LANCZOS
    )
)

imagen_tk = (
    ImageTk.PhotoImage(
        imagen_original
    )
)


# =========================================================
# BOTÓN
# =========================================================

boton = tk.Button(

    root,

    image=imagen_tk,

    borderwidth=0,
    highlightthickness=0,

    relief="flat",

    cursor="hand2"
)

boton.pack(
    fill="both",
    expand=True
)


# =========================================================
# DRAG & DROP DE IMÁGENES / TEXTO
# =========================================================

if DND_DISPONIBLE:
    try:
        boton.drop_target_register(
            DND_FILES,
            DND_TEXT
        )
        boton.dnd_bind(
            "<<Drop>>",
            manejar_drop
        )
        print(
            "Drag & Drop: activo (imágenes, archivos de texto y texto)."
        )
    except Exception as e:
        print(
            "No pude activar Drag & Drop:",
            e
        )


# =========================================================
# CLIC / ARRASTRE
# =========================================================

boton.bind(
    "<ButtonPress-1>",
    iniciar_arrastre
)

boton.bind(
    "<B1-Motion>",
    mover_masterx
)

boton.bind(
    "<ButtonRelease-1>",
    terminar_arrastre
)


# =========================================================
# CLIC DERECHO
# =========================================================

boton.bind(
    "<Button-3>",
    modo_manual
)


# =========================================================
# CLIC MEDIO
# =========================================================

boton.bind(
    "<Button-2>",
    abrir_menu_shortcuts
)


# =========================================================
# HOVER
# =========================================================

boton.bind(
    "<Enter>",
    mostrar_detalle_respuesta
)

boton.bind(
    "<Leave>",
    ocultar_detalle_respuesta
)


# =========================================================
# ESC
# =========================================================

root.bind(
    "<Escape>",
    ocultar_masterx_a_bandeja
)


# =========================================================
# SHORTCUTS GLOBALES
# =========================================================

registrar_shortcuts()


# =========================================================
# VIGILAR VENTANAS
# =========================================================

threading.Thread(

    target=
        vigilar_ventana,

    daemon=True

).start()


# =========================================================
# PRIMER ARRANQUE
# =========================================================

def flujo_primer_arranque():

    if not licencia_activa:
        abrir_configuracion_licencia(
            obligatoria=True,
            al_terminar=lambda: (
                abrir_configuracion_proveedor_actual(
                    obligatoria=True
                )
                if not proveedor_configurado()
                else None
            )
        )
        return

    if not proveedor_configurado():
        abrir_configuracion_proveedor_actual(
            obligatoria=True
        )


root.after(
    700,
    flujo_primer_arranque
)

# Buscar actualización unos segundos después del arranque.
# Se ejecuta en segundo plano y no bloquea OCR/IA.
root.after(
    2200,
    comprobar_actualizaciones_inicio
)


# =========================================================
# BANDEJA / MENU BAR
# =========================================================

iniciar_bandeja()

# =========================================================
# EJECUTAR
# =========================================================

root.mainloop()
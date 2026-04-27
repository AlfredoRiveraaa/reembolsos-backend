"""
Robot de Correos - Worker de segundo plano
============================================
Procesa automáticamente los correos de la bandeja de entrada
y envía las facturas XML a la API de reembolsos.

Se ejecuta de forma independiente de la API principal.
"""

import imaplib
import email
import os
import requests
import time
from dotenv import load_dotenv
from email.header import decode_header

load_dotenv()
EMAIL_USER = os.getenv("EMAIL_USUARIO")
EMAIL_PASS = os.getenv("EMAIL_PASSWORD")
API_URL = "http://127.0.0.1:8000/api/reembolsos/procesar-xml"
LOGIN_URL = os.getenv("API_LOGIN_URL", "http://127.0.0.1:8000/api/login")
ROBOT_API_CORREO = os.getenv("ROBOT_API_CORREO", EMAIL_USER)
ROBOT_API_PASSWORD = os.getenv("ROBOT_API_PASSWORD")


def obtener_token_api():
    """Hace login contra la API y retorna access_token."""
    if not ROBOT_API_CORREO or not ROBOT_API_PASSWORD:
        print("Faltan ROBOT_API_CORREO o ROBOT_API_PASSWORD en .env")
        return None

    try:
        respuesta = requests.post(
            LOGIN_URL,
            data={"username": ROBOT_API_CORREO, "password": ROBOT_API_PASSWORD},
            timeout=20,
        )
        if respuesta.status_code != 200:
            print(f"Login API fallido ({respuesta.status_code}): {respuesta.text}")
            return None

        payload = respuesta.json()
        token = payload.get("access_token")
        if not token:
            print("Login API sin access_token en la respuesta")
            return None

        print("Token JWT obtenido correctamente")
        return token
    except Exception as e:
        print(f"Error obteniendo token API: {str(e)}")
        return None

def limpiar_texto(texto):
    """Decodifica y limpia texto de correos con múltiples encodings."""
    if not texto: return ""
    decodificado, charset = decode_header(texto)[0]
    if isinstance(decodificado, bytes):
        return decodificado.decode(charset or "utf-8", errors="ignore")
    return decodificado

def leer_bandeja_y_procesar(token_api):
    """
    Lee los correos no leídos de Gmail y procesa los adjuntos XML/PDF.
    Envía los archivos a la API de reembolsos.
    """
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select("inbox")
        
        if not token_api:
            print("No hay token API para procesar correos")
            return False

        status, mensajes = mail.search(None, "UNSEEN")
        lista_ids = mensajes[0].split()
        if not lista_ids:
            return True
        lista_ids = lista_ids[-5:]  # Procesar últimos 5 correos

        for num_id in lista_ids:
            _, datos_msg = mail.fetch(num_id, "(RFC822)")
            for respuesta_part in datos_msg:
                if isinstance(respuesta_part, tuple):
                    msg = email.message_from_bytes(respuesta_part[1])
                    correo_remitente = limpiar_texto(msg.get("From")).split("<")[-1].replace(">", "").strip()
                    print(f"\nAnalizando correo de: {correo_remitente}")

                    contenido_xml = None
                    nombre_xml = None
                    lista_pdfs = [] 

                    for part in msg.walk():
                        if part.get_content_maintype() == "multipart" or part.get("Content-Disposition") is None: continue
                        nombre_archivo = part.get_filename()
                        
                        if nombre_archivo:
                            nombre_archivo = limpiar_texto(nombre_archivo)
                            ext = nombre_archivo.lower()
                            if ext.endswith(".xml"):
                                nombre_xml = nombre_archivo
                                contenido_xml = part.get_payload(decode=True)
                            elif ext.endswith(".pdf"):
                                lista_pdfs.append((nombre_archivo, part.get_payload(decode=True)))

                    procesado_con_exito = False
                    # --- NUEVO: Banderas de cuarentena ---
                    tiene_error = False
                    razon_error = ""

                    if contenido_xml:
                        print(f"XML encontrado: {nombre_xml}")
                        print(f"Se encontraron {len(lista_pdfs)} archivo(s) PDF adjuntos.")

                        ruta_temp_xml = f"temp_{nombre_xml}"
                        with open(ruta_temp_xml, "wb") as f: f.write(contenido_xml)

                        archivos_para_enviar = [("archivo", (nombre_xml, open(ruta_temp_xml, "rb"), "application/xml"))]
                        archivos_abiertos = [archivos_para_enviar[0][1][1]]
                        rutas_temp_pdfs = []

                        for i, (nom_pdf, cont_pdf) in enumerate(lista_pdfs):
                            ruta_temp_pdf = f"temp_pdf_{i}.pdf"
                            rutas_temp_pdfs.append(ruta_temp_pdf)
                            with open(ruta_temp_pdf, "wb") as f: f.write(cont_pdf)
                            
                            f_abierto = open(ruta_temp_pdf, "rb")
                            archivos_abiertos.append(f_abierto)
                            archivos_para_enviar.append(("pdfs", (nom_pdf, f_abierto, "application/pdf")))

                        print("Enviando paquete a la API...")
                        respuesta = requests.post(
                            API_URL,
                            files=archivos_para_enviar,
                            data={"correo": correo_remitente},
                            headers={"Authorization": f"Bearer {token_api}"},
                            timeout=60,
                        )
                        
                        for f in archivos_abiertos: f.close()
                        os.remove(ruta_temp_xml)
                        for r in rutas_temp_pdfs: os.remove(r)

                        if respuesta.status_code == 201:
                            print(f"API: Registro guardado (ID: {respuesta.json()['id']})")
                            procesado_con_exito = True
                        else:
                            if respuesta.status_code == 401:
                                print("API: Token invalido o expirado. Se renovara login.")
                                return False
                            if "duplicate key" in respuesta.text:
                                print("API: El archivo ya existía en la BD.")
                                procesado_con_exito = True
                            else: 
                                print(f"API Error: {respuesta.text}")
                                tiene_error = True
                                razon_error = "Rechazado por la API"
                    else:
                        print("Error: El correo no contiene ningún archivo XML adjunto.")
                        tiene_error = True
                        razon_error = "Falta archivo XML"

                    # --- CLASIFICACIÓN FINAL EN GMAIL ---
                    if procesado_con_exito:
                        if mail.copy(num_id, "PROCESADOS")[0] == 'OK':
                            mail.store(num_id, '+FLAGS', '\\Deleted')
                            print("Correo movido a 'PROCESADOS'.")
                    elif tiene_error:
                        try:
                            if mail.copy(num_id, "ERROR_XML")[0] == 'OK':
                                mail.store(num_id, '+FLAGS', '\\Deleted')
                                print(f"Correo movido a cuarentena 'ERROR_XML' ({razon_error}).")
                        except Exception as e:
                            print(f"No se pudo mover a ERROR_XML (¿Existe la etiqueta en Gmail?): {e}")

        mail.expunge()
        mail.close()
        return True

    except Exception as e:
        print(f"Error en robot_correos: {str(e)}")
        return True

def ejecutar_en_bucle(intervalo_segundos=60):
    """
    Ejecuta el robot continuamente cada X segundos.
    
    Args:
        intervalo_segundos: Tiempo de espera entre ejecuciones (por defecto 60s)
    """
    print(f"Robot de Correos iniciado - Verificando cada {intervalo_segundos}s...")
    token_api = obtener_token_api()

    while True:
        if not token_api:
            token_api = obtener_token_api()
            if not token_api:
                time.sleep(intervalo_segundos)
                continue

        token_valido = leer_bandeja_y_procesar(token_api)
        if not token_valido:
            token_api = None

        time.sleep(intervalo_segundos)

if __name__ == "__main__":
    ejecutar_en_bucle()

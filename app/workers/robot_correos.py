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
import re
import requests
import time
from dotenv import load_dotenv
from email.header import decode_header

from app.services.notificador import NotificadorCorreo

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
                    asunto_correo = limpiar_texto(msg.get("Subject", ""))
                    
                    print(f"\nAnalizando correo de: {correo_remitente}")
                    print(f"Asunto: {asunto_correo}")

                    # --- NUEVA LÓGICA DE DETECCIÓN DE FOLIO ---
                    match_folio = re.search(r"Folio:\s*([A-Fa-f0-9]{8})", asunto_correo, re.IGNORECASE)

                    es_actualizacion = False
                    folio_corto = None
                    nombre_solicitante = ""

                    if match_folio:
                        es_actualizacion = True
                        folio_corto = match_folio.group(1).upper()
                        print(f"Detectado correo de RESPUESTA/ACTUALIZACIÓN para el Folio: {folio_corto}")
                    else:
                    # Lógica original y nueva para correos nuevos
                        partes_asunto = asunto_correo.split("-")
                    id_trabajador = "" # Iniciamos vacío
                    
                    if len(partes_asunto) >= 3:
                        # Formato: Reembolso - Juan Perez - 12345
                        nombre_solicitante = partes_asunto[1].strip()
                        id_trabajador = partes_asunto[2].strip()
                    elif len(partes_asunto) == 2:
                        # Formato antiguo (por compatibilidad): Reembolso - Juan Perez
                        nombre_solicitante = partes_asunto[1].strip()

                    # --- EXTRAER ARCHIVOS ---
                    lista_xmls = []
                    lista_pdfs = []
                    archivos_invalidos = []

                    for part in msg.walk():
                        if part.get_content_maintype() == "multipart" or part.get("Content-Disposition") is None: continue
                        nombre_archivo = part.get_filename()
                        
                        if nombre_archivo:
                            nombre_archivo = limpiar_texto(nombre_archivo)
                            ext = nombre_archivo.lower()
                            if ext.endswith(".xml"):
                                lista_xmls.append((nombre_archivo, part.get_payload(decode=True)))
                            elif ext.endswith(".pdf"):
                                lista_pdfs.append((nombre_archivo, part.get_payload(decode=True)))
                            else:
                                # Si no es ni PDF ni XML, lo guardamos como inválido
                                archivos_invalidos.append(nombre_archivo)

                    # Contamos cuántos archivos llegaron
                    num_xmls = len(lista_xmls)
                    num_pdfs = len(lista_pdfs)
                    num_invalidos = len(archivos_invalidos)
                    
                    # Si hay al menos un XML, lo preparamos para el resto del código
                    nombre_xml = lista_xmls[0][0] if num_xmls > 0 else None
                    contenido_xml = lista_xmls[0][1] if num_xmls > 0 else None

                    procesado_con_exito = False
                    tiene_error = False
                    razon_error = ""
                    mensaje_error_usuario = ""
                    instrucciones_usuario = ""

                    num_pdfs = len(lista_pdfs)

                    # --- LÓGICA DE DETECCIÓN DE ERRORES AL USUARIO ---
                    if not es_actualizacion:
                        
                        # 1. NUEVA VALIDACIÓN ESTRICTA DEL ASUNTO
                        # Verificamos que existan ambas variables y que la primera palabra contenga "Reembolso"
                        if not nombre_solicitante or not id_trabajador or "reembolso" not in partes_asunto[0].lower().strip():
                            tiene_error = True
                            razon_error = "Asunto sin formato válido"
                            mensaje_error_usuario = f"El asunto de tu correo no sigue el formato estricto. Recibimos: '{asunto_correo}'."
                            instrucciones_usuario = "El asunto DEBE contener tres partes separadas por guiones: 'Reembolso - Tu Nombre - Tu ID'. (Ejemplo: Reembolso - Juan Pérez - 2026001)."
                            
                        # 2. Validaciones de archivos (ya las tenías)
                        elif num_xmls == 0:
                            tiene_error = True
                            razon_error = "Falta archivo XML"
                            mensaje_error_usuario = "No se detectó ningún archivo .xml adjunto."
                            instrucciones_usuario = "Debes adjuntar el archivo XML original emitido por el proveedor."
                            
                        elif num_xmls > 1:
                            tiene_error = True
                            razon_error = "Exceso de archivos XML"
                            mensaje_error_usuario = f"Se detectaron {num_xmls} archivos XML en tu correo."
                            instrucciones_usuario = "Solo puedes enviar un (1) archivo XML por correo. Recuerda que cada solicitud debe tramitarse en un correo independiente."

                        elif num_invalidos > 0:
                            tiene_error = True
                            razon_error = "Formato de archivo no permitido"
                            nombres_malos = ", ".join(archivos_invalidos)
                            mensaje_error_usuario = f"Adjuntaste archivos con formatos no aceptados ({nombres_malos})."
                            instrucciones_usuario = "El sistema NO procesa imágenes (JPG, PNG), documentos de Word ni Excel. Por favor, convierte todos tus comprobantes y recetas a formato PDF y vuelve a enviar el correo."
                            
                        elif num_pdfs == 0:
                            tiene_error = True
                            razon_error = "Falta Factura o Receta en PDF"
                            mensaje_error_usuario = "No adjuntaste los archivos PDF requeridos."
                            instrucciones_usuario = "Es obligatorio adjuntar la Factura Original (PDF) y la Orden Médica (PDF)."
                            
                        elif num_pdfs > 2: 
                            tiene_error = True
                            razon_error = "Exceso de archivos PDF"
                            mensaje_error_usuario = f"Se detectaron {num_pdfs} archivos PDF en tu correo."
                            instrucciones_usuario = "Separa tus solicitudes. Cada correo es una solicitud independiente y solo debe tener el PDF de la factura y el PDF de su receta."

                    if not tiene_error:
                        # --- PREPARAMOS LOS ARCHIVOS (PDFs y XMLs si los hay) ---
                        archivos_para_enviar = []
                        rutas_temp = []
                        archivos_abiertos = []

                        # Agregamos el XML si viene (puede ser un correo nuevo o una corrección de XML)
                        if contenido_xml:
                            ruta_temp_xml = f"temp_{nombre_xml}"
                            rutas_temp.append(ruta_temp_xml)
                            with open(ruta_temp_xml, "wb") as f:
                                f.write(contenido_xml)
                            f_abierto = open(ruta_temp_xml, "rb")
                            archivos_abiertos.append(f_abierto)

                            # Si es nuevo, FastAPI lo espera como 'archivo'. Si es actualización, como 'archivos'
                            key_xml = "archivos" if es_actualizacion else "archivo"
                            archivos_para_enviar.append((key_xml, (nombre_xml, f_abierto, "application/xml")))

                        # Agregamos los PDFs
                        for i, (nom_pdf, cont_pdf) in enumerate(lista_pdfs):
                            ruta_temp_pdf = f"temp_pdf_{i}.pdf"
                            rutas_temp.append(ruta_temp_pdf)
                            with open(ruta_temp_pdf, "wb") as f:
                                f.write(cont_pdf)
                            f_abierto = open(ruta_temp_pdf, "rb")
                            archivos_abiertos.append(f_abierto)

                            key_pdf = "archivos" if es_actualizacion else "pdfs"
                            archivos_para_enviar.append((key_pdf, (nom_pdf, f_abierto, "application/pdf")))

                        if not archivos_para_enviar:
                            print("Error: El correo de respuesta no tiene ningún archivo adjunto.")
                            tiene_error = True
                            razon_error = "Respuesta sin adjuntos"
                        else:
                            # --- ENVIAMOS A LA API CORRESPONDIENTE ---
                            if es_actualizacion:
                                print(f"Enviando archivos de corrección a la API (Folio {folio_corto})...")
                                url_destino = f"http://127.0.0.1:8000/api/reembolsos/actualizar-expediente/{folio_corto}"
                                respuesta = requests.post(
                                    url_destino,
                                    files=archivos_para_enviar,
                                    headers={"Authorization": f"Bearer {token_api}"},
                                    timeout=60,
                                )
                            else:
                                print("Enviando paquete nuevo a la API...")
                                respuesta = requests.post(
                                    API_URL,
                                    files=archivos_para_enviar,
                                data={
                                    "correo": correo_remitente, 
                                    "nombre_solicitante": nombre_solicitante,
                                    "id_trabajador": id_trabajador
                                },
                                    headers={"Authorization": f"Bearer {token_api}"},
                                    timeout=60,
                                )

                            # Limpieza de temporales
                            for f in archivos_abiertos:
                                f.close()
                            for r in rutas_temp:
                                os.remove(r)

                            # Verificamos respuesta
                            if respuesta.status_code in [200, 201]:
                                print(f"API OK: {respuesta.json()}")
                                procesado_con_exito = True
                            else:
                                print(f"API Error ({respuesta.status_code}): {respuesta.text}")
                                tiene_error = True
                                razon_error = "Rechazado por la API"

                                # Detectar si fue por estar Duplicado en BD
                                if "duplicate key" in respuesta.text.lower() or "integrityerror" in respuesta.text.lower():
                                    razon_error = "Factura Duplicada en Sistema"
                                    mensaje_error_usuario = "El archivo XML que enviaste ya fue registrado previamente y tiene un folio asignado."
                                    instrucciones_usuario = "Si Recursos Humanos te solicitó corregir un documento, NO debes enviar un correo nuevo. Debes buscar el correo que te envió RH y darle clic en 'Responder' adjuntando la corrección."
                                else:
                                    mensaje_error_usuario = "Los datos dentro de tu archivo XML no pasaron la validación fiscal del sistema."
                                    instrucciones_usuario = "Por favor, verifica que estés enviando un XML válido y vigente."

                    # --- ENVÍO DE FEEDBACK AL TRABAJADOR ---
                    if tiene_error and mensaje_error_usuario and correo_remitente:
                        print(f"Enviando correo de auto-corrección al trabajador: {razon_error}")
                        try:
                            NotificadorCorreo.enviar_error_formato(
                                correo_remitente,
                                mensaje_error_usuario,
                                instrucciones_usuario,
                            )
                        except Exception as e:
                            print(f"Fallo al enviar correo de feedback: {e}")

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

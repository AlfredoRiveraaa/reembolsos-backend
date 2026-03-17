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

def limpiar_texto(texto):
    if not texto: return ""
    decodificado, charset = decode_header(texto)[0]
    if isinstance(decodificado, bytes):
        return decodificado.decode(charset or "utf-8", errors="ignore")
    return decodificado

def leer_bandeja_y_procesar():
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select("inbox")
        
        status, mensajes = mail.search(None, "UNSEEN")
        lista_ids = mensajes[0].split()
        if not lista_ids: return
        lista_ids = lista_ids[-5:] 

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
                        respuesta = requests.post(API_URL, files=archivos_para_enviar, data={"correo": correo_remitente})
                        
                        for f in archivos_abiertos: f.close()
                        os.remove(ruta_temp_xml)
                        for r in rutas_temp_pdfs: os.remove(r)

                        if respuesta.status_code == 201:
                            print(f"API: Registro guardado (ID: {respuesta.json()['id']})")
                            procesado_con_exito = True
                        else:
                            if "duplicate key" in respuesta.text:
                                print("API: El archivo ya existía en la BD.")
                                procesado_con_exito = True
                            else: print(f"API Error: {respuesta.text}")

                    if procesado_con_exito:
                        if mail.copy(num_id, "PROCESADOS")[0] == 'OK':
                            mail.store(num_id, '+FLAGS', '\\Deleted')
                            print("Correo movido a 'PROCESADOS'.")

        mail.expunge()
        mail.logout()

    except Exception as e: print(f"Error crítico: {e}")

if __name__ == "__main__":
    minutos_espera = 5
    print(f"MODO AUTOMÁTICO ACTIVADO. El robot revisará tu correo cada {minutos_espera} minutos.")
    print("Presiona Ctrl + C para detenerlo.\n")
    while True:
        leer_bandeja_y_procesar()
        print(f"Durmiendo... Volveré en {minutos_espera} minutos.")
        time.sleep(minutos_espera * 60)
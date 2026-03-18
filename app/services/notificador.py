import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
from typing import Optional
from datetime import datetime

load_dotenv()

EMAIL_REMITENTE = os.getenv("EMAIL_USUARIO")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

class NotificadorCorreo:
    """Servicio centralizado para enviar notificaciones por correo electrónico."""
    
    @staticmethod
    def _obtener_conexion_smtp():
        """Establece conexión SMTP con Gmail."""
        try:
            servidor = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
            servidor.starttls()
            servidor.login(EMAIL_REMITENTE, EMAIL_PASSWORD)
            return servidor
        except Exception as e:
            print(f"Error conectando a SMTP: {str(e)}")
            raise

    @staticmethod
    def _enviar_correo(destinatario: str, asunto: str, cuerpo_html: str) -> bool:
        """
        Envía un correo electrónico.
        
        Args:
            destinatario: Email del receptor
            asunto: Asunto del correo
            cuerpo_html: Contenido HTML del correo
            
        Returns:
            True si se envió exitosamente, False en caso contrario
        """
        try:
            servidor = NotificadorCorreo._obtener_conexion_smtp()
            
            # Crear mensaje
            mensaje = MIMEMultipart("alternative")
            mensaje["From"] = EMAIL_REMITENTE
            mensaje["To"] = destinatario
            mensaje["Subject"] = asunto
            
            # Adjuntar contenido HTML
            parte_html = MIMEText(cuerpo_html, "html", "utf-8")
            mensaje.attach(parte_html)
            
            # Enviar
            servidor.send_message(mensaje)
            servidor.quit()
            
            print(f"✓ Correo enviado a {destinatario}: {asunto}")
            return True
            
        except Exception as e:
            print(f"✗ Error enviando correo a {destinatario}: {str(e)}")
            return False

    @staticmethod
    def enviar_acuse_recibo(correo_solicitante: str, uuid_factura: str, monto: float, 
                            nombre_proveedor: str, fecha_recepcion: Optional[datetime] = None) -> bool:
        """
        Envía acuse de recibo cuando se procesa una factura XML.
        
        Args:
            correo_solicitante: Email del empleado que envió la factura
            uuid_factura: UUID único de la factura procesada
            monto: Monto de la factura
            nombre_proveedor: Nombre del proveedor/emisor
            fecha_recepcion: Fecha de recepción (por defecto ahora)
            
        Returns:
            True si se envió exitosamente
        """
        if not fecha_recepcion:
            fecha_recepcion = datetime.now()
        
        asunto = f"✓ Acuse de Recibo - Factura {uuid_factura[:8]}"
        
        cuerpo_html = f"""
        <html>
            <body style="font-family: Arial, sans-serif; background-color: #f5f5f5; padding: 20px;">
                <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                    
                    <h2 style="color: #27ae60; border-bottom: 3px solid #27ae60; padding-bottom: 10px;">
                        ✓ Acuse de Recibo
                    </h2>
                    
                    <p>Estimado empleado,</p>
                    
                    <p>Su factura ha sido <strong>correctamente recibida y registrada</strong> en el sistema de reembolsos.</p>
                    
                    <div style="background-color: #ecf0f1; padding: 15px; border-left: 4px solid #27ae60; margin: 20px 0;">
                        <p style="margin: 5px 0;"><strong>UUID de la Factura:</strong> {uuid_factura}</p>
                        <p style="margin: 5px 0;"><strong>Proveedor/Emisor:</strong> {nombre_proveedor}</p>
                        <p style="margin: 5px 0;"><strong>Monto:</strong> ${monto:,.2f}</p>
                        <p style="margin: 5px 0;"><strong>Fecha de Recepción:</strong> {fecha_recepcion.strftime('%d/%m/%Y %H:%M')}</p>
                    </div>
                    
                    <h3 style="color: #2c3e50;">Próximos Pasos:</h3>
                    <ol>
                        <li>Tu solicitud pasará a revisión de Recursos Humanos</li>
                        <li>Recibirás un correo de notificación cuando se valide o rechace</li>
                        <li>En caso de rechazo, se especificarán los motivos</li>
                    </ol>
                    
                    <p style="color: #7f8c8d; font-size: 12px; margin-top: 30px; border-top: 1px solid #ecf0f1; padding-top: 10px;">
                        ⚠ Este es un correo automático. Por favor no respondas a este correo.
                    </p>
                </div>
            </body>
        </html>
        """
        
        return NotificadorCorreo._enviar_correo(correo_solicitante, asunto, cuerpo_html)

    @staticmethod
    def enviar_validacion(correo_solicitante: str, uuid_factura: str, monto: float, comentarios_rh: Optional[str] = None) -> bool:
        """
        Notifica al empleado que su solicitud fue VALIDADA por RH.
        
        Args:
            correo_solicitante: Email del empleado
            uuid_factura: UUID de la factura
            monto: Monto aprobado
            comentarios_rh: Comentarios opcionales de Recursos Humanos
            
        Returns:
            True si se envió exitosamente
        """
        asunto = f"✓ Solicitud APROBADA - {uuid_factura[:8]}"
        
        # Si RH escribió algo, armamos una cajita bonita de comentarios
        seccion_comentarios = ""
        if comentarios_rh:
            seccion_comentarios = f"""
            <h3 style="color: #2c3e50; margin-top: 20px;">Comentarios de Recursos Humanos:</h3>
            <p style="background-color: #e8f8f5; padding: 12px; border-radius: 4px; color: #16a085; font-style: italic;">
                "{comentarios_rh}"
            </p>
            """
        
        cuerpo_html = f"""
        <html>
            <body style="font-family: Arial, sans-serif; background-color: #f5f5f5; padding: 20px;">
                <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                    <h2 style="color: #27ae60; border-bottom: 3px solid #27ae60; padding-bottom: 10px;">
                        ✓ SOLICITUD APROBADA
                    </h2>
                    <p>¡Excelentes noticias!</p>
                    <p>Tu solicitud de reembolso ha sido <strong>VALIDADA Y APROBADA</strong> por Recursos Humanos.</p>
                    
                    <div style="background-color: #d5f4e6; padding: 15px; border-left: 4px solid #27ae60; margin: 20px 0;">
                        <p style="margin: 5px 0;"><strong>UUID de la Factura:</strong> {uuid_factura}</p>
                        <p style="margin: 5px 0;"><strong>Monto Aprobado:</strong> <span style="color: #27ae60; font-weight: bold; font-size: 18px;">${monto:,.2f}</span></p>
                    </div>
                    
                    {seccion_comentarios}
                    
                    <h3 style="color: #2c3e50;">Pasos Siguientes:</h3>
                    <p>El pago será procesado conforme a los procedimientos establecidos. Recibirás una confirmación adicional una vez que el reembolso se haya efectuado.</p>
                    <p style="color: #27ae60; font-weight: bold;">Gracias por tu paciencia.</p>
                    
                    <p style="color: #7f8c8d; font-size: 12px; margin-top: 30px; border-top: 1px solid #ecf0f1; padding-top: 10px;">
                        ⚠ Este es un correo automático. Por favor no respondas a este correo.
                    </p>
                </div>
            </body>
        </html>
        """
        return NotificadorCorreo._enviar_correo(correo_solicitante, asunto, cuerpo_html)

    @staticmethod
    def enviar_rechazo(correo_solicitante: str, uuid_factura: str, monto: float, motivo_rechazo: str) -> bool:
        """
        Notifica al empleado que su solicitud fue RECHAZADA por RH.
        
        Args:
            correo_solicitante: Email del empleado
            uuid_factura: UUID de la factura
            monto: Monto de la solicitud rechazada
            motivo_rechazo: Razón del rechazo
            
        Returns:
            True si se envió exitosamente
        """
        asunto = f"✗ Solicitud RECHAZADA - {uuid_factura[:8]}"
        
        cuerpo_html = f"""
        <html>
            <body style="font-family: Arial, sans-serif; background-color: #f5f5f5; padding: 20px;">
                <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                    <h2 style="color: #e74c3c; border-bottom: 3px solid #e74c3c; padding-bottom: 10px;">
                        ✗ SOLICITUD RECHAZADA
                    </h2>
                    <p>Lamentablemente, tu solicitud de reembolso ha sido <strong>RECHAZADA</strong> por Recursos Humanos.</p>
                    
                    <div style="background-color: #fadbd8; padding: 15px; border-left: 4px solid #e74c3c; margin: 20px 0;">
                        <p style="margin: 5px 0;"><strong>UUID de la Factura:</strong> {uuid_factura}</p>
                        <p style="margin: 5px 0;"><strong>Monto:</strong> ${monto:,.2f}</p>
                    </div>
                    
                    <h3 style="color: #c0392b; margin-top: 20px;">Motivo del Rechazo:</h3>
                    <p style="background-color: #fdeaea; padding: 12px; border-radius: 4px; color: #c0392b; font-style: italic;">
                        "{motivo_rechazo}"
                    </p>
                    
                    <h3 style="color: #2c3e50;">¿Qué puedes hacer?</h3>
                    <ul>
                        <li>Revisa el motivo del rechazo indicado arriba</li>
                        <li>Corrige lo necesario en tu documentación</li>
                        <li>Contacta a Recursos Humanos si tienes dudas</li>
                    </ul>
                    
                    <p style="color: #7f8c8d; font-size: 12px; margin-top: 30px; border-top: 1px solid #ecf0f1; padding-top: 10px;">
                        ⚠ Este es un correo automático. Por favor no respondas a este correo.
                    </p>
                </div>
            </body>
        </html>
        """
        return NotificadorCorreo._enviar_correo(correo_solicitante, asunto, cuerpo_html)

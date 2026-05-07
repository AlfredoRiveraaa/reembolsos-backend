import os
import shutil
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List, Optional

from app.db.database import SessionLocal
from app.db import models
from app.api import schemas
from app.core.security import obtener_usuario_actual
from app.services.extractor_xml import extraer_datos_factura
from app.services.notificador import NotificadorCorreo

router = APIRouter(
    prefix="/api/reembolsos",
    tags=["reembolsos"],
    dependencies=[Depends(obtener_usuario_actual)],
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ==========================================
# ENDPOINTS
# ==========================================

@router.get("", response_model=List[schemas.ReembolsoResponse])
def obtener_reembolsos(db: Session = Depends(get_db)):
    """Obtiene lista de todos los reembolsos registrados."""
    reembolsos = db.query(models.SolicitudReembolso).all()
    return reembolsos

@router.get("/{reembolso_id}", response_model=schemas.ReembolsoResponse)
def obtener_reembolso_por_id(
    reembolso_id: int,
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(obtener_usuario_actual),
):
    """
    Obtiene los detalles de un reembolso específico por su ID numérico.
    """
    reembolso = db.query(models.SolicitudReembolso).filter(models.SolicitudReembolso.id == reembolso_id).first()

    if not reembolso:
        raise HTTPException(
            status_code=404,
            detail="El reembolso solicitado no existe",
        )

    return reembolso

@router.get("/{reembolso_id}/archivo")
def obtener_archivo_reembolso(
    reembolso_id: int,
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(obtener_usuario_actual),
):
    reembolso = db.query(models.SolicitudReembolso).filter(models.SolicitudReembolso.id == reembolso_id).first()

    if not reembolso:
        raise HTTPException(status_code=404, detail="Reembolso no encontrado")

    if not reembolso.link_expediente:
        raise HTTPException(status_code=404, detail="Este reembolso no tiene un expediente asociado")

    base_dir = reembolso.link_expediente

    if not os.path.exists(base_dir):
        raise HTTPException(status_code=404, detail=f"Carpeta no encontrada físicamente: {base_dir}")

    try:
        archivos = os.listdir(base_dir)
        pdf_file = next((f for f in archivos if f.lower().endswith(".pdf")), None)

        if not pdf_file:
            raise HTTPException(status_code=404, detail="No se encontró ningún PDF en la carpeta")

        file_path = os.path.join(base_dir, pdf_file)

        # Devolvemos el PDF al frontend
        return FileResponse(file_path, media_type="application/pdf", filename=pdf_file)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al leer la carpeta: {str(e)}")

@router.post("", response_model=schemas.ReembolsoResponse, status_code=201)
def crear_reembolso(reembolso: schemas.ReembolsoCreate, db: Session = Depends(get_db)):
    """Crea un nuevo reembolso manualmente."""
    nuevo_reembolso = models.SolicitudReembolso(
        uuid=reembolso.uuid,
        monto=reembolso.monto,
        correo_solicitante=reembolso.correo_solicitante,
        nombre_solicitante=reembolso.nombre_solicitante,
        nombre_proveedor=reembolso.nombre_proveedor,
        estatus="PENDIENTE",
        forma_pago=reembolso.forma_pago,
        rfc_emisor=reembolso.rfc_emisor,
        fecha_factura=reembolso.fecha_factura,
        link_expediente=reembolso.link_expediente
    )
    
    try:
        db.add(nuevo_reembolso)
        db.commit()
        db.refresh(nuevo_reembolso)
        return nuevo_reembolso
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Error al guardar: {str(e)}")
    
@router.post("/procesar-xml", response_model=schemas.ReembolsoResponse, status_code=201)
async def procesar_factura_xml(
    correo: str = Form(...),
    nombre_solicitante: str = Form(...),
    archivo: UploadFile = File(...),
    pdfs: List[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """Procesa un archivo XML de factura y lo guarda en la BD con PDFs adjuntos."""
    id_unico = str(uuid.uuid4())
    ruta_temporal = f"temp_{id_unico}_{archivo.filename}"
    
    with open(ruta_temporal, "wb") as buffer:
        shutil.copyfileobj(archivo.file, buffer)
        
    resultado = extraer_datos_factura(ruta_temporal)
    
    if os.path.exists(ruta_temporal): 
        os.remove(ruta_temporal)
        
    if resultado["status"] != "success":
        raise HTTPException(status_code=400, detail=resultado["mensaje"])
        
    datos = resultado["datos"]
    
    ruta_carpeta_expediente = None
    pdfs_validos = [p for p in pdfs if p.filename]
    
    if pdfs_validos:
        ruta_carpeta_expediente = f"expedientes_pdf/{datos['uuid']}"
        os.makedirs(ruta_carpeta_expediente, exist_ok=True)
        
        for pdf in pdfs_validos:
            ruta_pdf_final = f"{ruta_carpeta_expediente}/{pdf.filename}"
            with open(ruta_pdf_final, "wb") as buffer_pdf:
                shutil.copyfileobj(pdf.file, buffer_pdf)
    
    nuevo_reembolso = models.SolicitudReembolso(
        uuid=datos["uuid"],
        monto=datos["monto_total"],
        correo_solicitante=correo,
        nombre_solicitante=nombre_solicitante,
        nombre_proveedor=datos["nombre_emisor"],
        estatus="PENDIENTE",
        rfc_emisor=datos["rfc_emisor"],
        link_expediente=ruta_carpeta_expediente 
    )
    
    try:
        db.add(nuevo_reembolso)
        db.commit()
        db.refresh(nuevo_reembolso)
        
        background_tasks.add_task(
            NotificadorCorreo.enviar_acuse_recibo,
            correo_solicitante=correo,
            uuid_factura=datos["uuid"],
            monto=datos["monto_total"],
            nombre_proveedor=datos["nombre_emisor"],
            fecha_recepcion=nuevo_reembolso.fecha_recepcion
        )
        
        return nuevo_reembolso
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Error BD: {str(e)}")

@router.patch("/{reembolso_id}/iniciar-revision", response_model=schemas.ReembolsoResponse)
def iniciar_revision(
    reembolso_id: int,
    db: Session = Depends(get_db),
    usuario_actual: schemas.UsuarioResponse = Depends(obtener_usuario_actual)
):
    """Cambia el estatus a 'EN REVISIÓN' y bloquea el reembolso para otros administradores."""
    reembolso = db.query(models.SolicitudReembolso).filter(models.SolicitudReembolso.id == reembolso_id).first()
    
    if not reembolso:
        raise HTTPException(status_code=404, detail="Reembolso no encontrado")
    
    # Validar que no esté siendo revisado por otra persona
    if reembolso.estatus == "EN REVISIÓN" and reembolso.revisado_por != usuario_actual.id:
        raise HTTPException(status_code=403, detail="Este reembolso ya está siendo revisado por otro administrador.")
    
    # Validar que no esté ya resuelto
    if reembolso.estatus in ["VALIDADO", "RECHAZADO", "APROBADO"]:
        raise HTTPException(status_code=400, detail="El reembolso ya fue procesado y no puede ser revisado nuevamente.")

    reembolso.estatus = "EN REVISIÓN"
    reembolso.revisado_por = usuario_actual.id
    
    db.commit()
    db.refresh(reembolso)
    return reembolso


@router.put("/{reembolso_id}/estatus", response_model=schemas.ReembolsoResponse)
def actualizar_estatus(
    reembolso_id: int, 
    nuevo_estatus: str, 
    comentarios_rh: str = None,
    db: Session = Depends(get_db),
    usuario_actual: schemas.UsuarioResponse = Depends(obtener_usuario_actual),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """Actualiza el estatus final de un reembolso y envía notificaciones automáticas."""
    reembolso = db.query(models.SolicitudReembolso).filter(models.SolicitudReembolso.id == reembolso_id).first()
    
    if not reembolso:
        raise HTTPException(status_code=404, detail="Reembolso no encontrado")
        
    # Opcional: Validar que quien aprueba es quien inició la revisión
    # if reembolso.revisado_por and reembolso.revisado_por != usuario_actual.id:
    #     raise HTTPException(status_code=403, detail="Solo el administrador que inició la revisión puede aprobarlo.")
    
    reembolso.estatus = nuevo_estatus.upper()
    
    # Guardamos los comentarios en la base de datos (reutilizando tu columna)
    if comentarios_rh:
        reembolso.mensaje = comentarios_rh
        
    reembolso.fecha_resolucion = datetime.utcnow()
        
    db.commit()
    db.refresh(reembolso)
    
    # Enviar notificación en segundo plano según el estatus
    if reembolso.estatus in ["VALIDADA", "VALIDADO", "APROBADO"]:
        background_tasks.add_task(
            NotificadorCorreo.enviar_validacion,
            correo_solicitante=reembolso.correo_solicitante,
            uuid_factura=reembolso.uuid,
            monto=float(reembolso.monto),
            comentarios_rh=comentarios_rh
        )
    elif reembolso.estatus in ["RECHAZADA", "RECHAZADO"]:
        background_tasks.add_task(
            NotificadorCorreo.enviar_rechazo,
            correo_solicitante=reembolso.correo_solicitante,
            uuid_factura=reembolso.uuid,
            monto=float(reembolso.monto),
            motivo_rechazo=comentarios_rh or "No cumple con los requisitos fiscales."
        )
    
    return reembolso
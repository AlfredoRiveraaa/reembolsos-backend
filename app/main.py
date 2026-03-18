import os
import shutil
import uuid
from fastapi import FastAPI, Depends, HTTPException, File, UploadFile, Form, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List, Optional

from app.db.database import engine, SessionLocal
from app.db import models
from app.api import schemas
from app.services.extractor_xml import extraer_datos_factura
from app.services.notificador import NotificadorCorreo

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="API Reembolsos DRH", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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

@app.get("/")
def read_root():
    return {"mensaje": "¡El cerebro de Python está vivo!"}

@app.get("/api/reembolsos", response_model=List[schemas.ReembolsoResponse])
def obtener_reembolsos(db: Session = Depends(get_db)):
    reembolsos = db.query(models.SolicitudReembolso).all()
    return reembolsos

@app.post("/api/reembolsos", response_model=schemas.ReembolsoResponse, status_code=201)
def crear_reembolso(reembolso: schemas.ReembolsoCreate, db: Session = Depends(get_db)):
    nuevo_reembolso = models.SolicitudReembolso(
        uuid=reembolso.uuid,
        monto=reembolso.monto,
        correo_solicitante=reembolso.correo_solicitante,
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
    
@app.post("/api/reembolsos/procesar-xml", response_model=schemas.ReembolsoResponse, status_code=201)
async def procesar_factura_xml(
    correo: str = Form(...),
    archivo: UploadFile = File(...),
    pdfs: List[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
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
        nombre_proveedor=datos["nombre_emisor"],
        estatus="PENDIENTE",
        rfc_emisor=datos["rfc_emisor"],
        link_expediente=ruta_carpeta_expediente 
    )
    
    try:
        db.add(nuevo_reembolso)
        db.commit()
        db.refresh(nuevo_reembolso)
        
        # ⚡ NUEVO: Enviar acuse en segundo plano (No hace esperar a la terminal)
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

@app.put("/api/reembolsos/{reembolso_id}/estatus", response_model=schemas.ReembolsoResponse)
def actualizar_estatus(
    reembolso_id: int, 
    nuevo_estatus: str, 
    comentarios_rh: str = None,
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    reembolso = db.query(models.SolicitudReembolso).filter(models.SolicitudReembolso.id == reembolso_id).first()
    
    if not reembolso:
        raise HTTPException(status_code=404, detail="Reembolso no encontrado")
    
    reembolso.estatus = nuevo_estatus.upper()
    
    # Guardamos los comentarios en la base de datos (reutilizando tu columna)
    if comentarios_rh:
        reembolso.mensaje_rechazo = comentarios_rh
        
    db.commit()
    db.refresh(reembolso)
    
    # ⚡ NUEVO: Enviar notificación en segundo plano según el estatus
    if reembolso.estatus == "VALIDADA":
        background_tasks.add_task(
            NotificadorCorreo.enviar_validacion,
            correo_solicitante=reembolso.correo_solicitante,
            uuid_factura=reembolso.uuid,
            monto=float(reembolso.monto),
            comentarios_rh=comentarios_rh
        )
    elif reembolso.estatus == "RECHAZADA":
        background_tasks.add_task(
            NotificadorCorreo.enviar_rechazo,
            correo_solicitante=reembolso.correo_solicitante,
            uuid_factura=reembolso.uuid,
            monto=float(reembolso.monto),
            motivo_rechazo=comentarios_rh or "No cumple con los requisitos fiscales."
        )
    
    return reembolso
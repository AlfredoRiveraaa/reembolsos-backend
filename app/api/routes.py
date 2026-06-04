import os
import shutil
import mimetypes
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
def obtener_reembolsos(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(obtener_usuario_actual),
):
    query = db.query(models.SolicitudReembolso)

    # Si NO es administrador, filtramos por sus días asignados
    if usuario_actual.rol != "ADMIN" and usuario_actual.dias_asignados:
        try:
            # Convertimos "1,3,5" en una lista de enteros [1, 3, 5] (Lunes=1, Domingo=7)
            dias_permitidos = [int(d.strip()) for d in usuario_actual.dias_asignados.split(",") if d.strip()]

            # Traemos los reembolsos ordenados y los filtramos en Python por fecha_recepcion
            reembolsos_db = query.order_by(models.SolicitudReembolso.fecha_recepcion.desc()).all()

            reembolsos_filtrados = []
            for r in reembolsos_db:
                if r.fecha_recepcion:
                    # isoweekday() da 1 para Lunes, 7 para Domingo
                    if r.fecha_recepcion.isoweekday() in dias_permitidos:
                        reembolsos_filtrados.append(r)

            # Aplicamos skip y limit después de filtrar
            return reembolsos_filtrados[skip : skip + limit]

        except Exception as e:
            print(f"Error al filtrar por días: {e}")
            # Si hay error, por seguridad mostramos todo
            pass

    # Si es ADMIN o hubo un error al leer los días, devolvemos todo normal
    reembolsos = query.order_by(models.SolicitudReembolso.fecha_recepcion.desc()).offset(skip).limit(limit).all()
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

@router.get("/{reembolso_id}/archivos", response_model=List[str])
def listar_archivos_reembolso(
    reembolso_id: int,
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(obtener_usuario_actual),
):
    reembolso = db.query(models.SolicitudReembolso).filter(models.SolicitudReembolso.id == reembolso_id).first()

    if not reembolso or not reembolso.link_expediente:
        return []

    base_dir = reembolso.link_expediente

    if not os.path.exists(base_dir):
        return []

    try:
        return [f for f in os.listdir(base_dir) if os.path.isfile(os.path.join(base_dir, f))]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al leer carpeta: {str(e)}")

@router.get("/{reembolso_id}/archivo/{nombre_archivo}")
def obtener_archivo_especifico(
    reembolso_id: int,
    nombre_archivo: str,
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(obtener_usuario_actual),
):
    reembolso = db.query(models.SolicitudReembolso).filter(models.SolicitudReembolso.id == reembolso_id).first()

    if not reembolso or not reembolso.link_expediente:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")

    base_dir = reembolso.link_expediente
    file_path = os.path.join(base_dir, nombre_archivo)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Archivo no encontrado")

    media_type, _ = mimetypes.guess_type(nombre_archivo)
    if not media_type:
        media_type = "application/octet-stream"

    return FileResponse(file_path, media_type=media_type, filename=nombre_archivo)

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

        archivo.file.seek(0)
        ruta_xml = os.path.join(ruta_carpeta_expediente, archivo.filename)
        with open(ruta_xml, "wb") as f_xml:
            f_xml.write(archivo.file.read())
        
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
        forma_pago=datos.get("forma_pago"),
        rfc_emisor=datos["rfc_emisor"],
        fecha_factura=datos.get("fecha_factura"),
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
        
    # --- NUEVO: BLOQUEO OPTIMISTA ---
    # Si intentan aprobar o rechazar algo que YA fue aprobado o rechazado por alguien más
    estados_finales = ["VALIDADA", "VALIDADO", "APROBADO", "RECHAZADA", "RECHAZADO"]
    if nuevo_estatus.upper() in estados_finales:
        if reembolso.estatus in estados_finales:
            raise HTTPException(
                status_code=409, # 409 significa Conflicto
                detail="¡Alto! Esta solicitud acaba de ser procesada por otro compañero."
            )
    # --------------------------------

    # Opcional: Validar que quien aprueba es quien inició la revisión
    # if reembolso.revisado_por and reembolso.revisado_por != usuario_actual.id:
    #     raise HTTPException(status_code=403, detail="Solo el administrador que inició la revisión puede aprobarlo.")
    
    reembolso.estatus = nuevo_estatus.upper()
    
    # Guardamos los comentarios en la base de datos (reutilizando tu columna)
    if comentarios_rh:
        reembolso.mensaje = comentarios_rh

    reembolso.revisado_por = usuario_actual.id
        
    reembolso.fecha_resolucion = datetime.now()
        
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
    elif reembolso.estatus in [
        "INFO_SOLICITADA",
        "SOLICITUD INFORMACION",
        "SOLICITUD DE INFORMACION",
        "SOLICITUD_INFORMACION",
        "SOLICITUD DE INFORMACIÓN",
        "SOLICITUD INFORMACIÓN",
        "INFORMACION",
        "INFORMACIÓN",
        "INFORMACION_ADICIONAL",
        "INFORMACIÓN_ADICIONAL",
    ]:
        background_tasks.add_task(
            NotificadorCorreo.enviar_solicitud_informacion,
            correo_solicitante=reembolso.correo_solicitante,
            uuid_factura=reembolso.uuid,
            motivo=comentarios_rh or "Se requiere información adicional para continuar con el trámite."
        )
    
    return reembolso


@router.post("/actualizar-expediente/{folio_corto}")
def actualizar_expediente(
    folio_corto: str,
    archivos: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(obtener_usuario_actual)
):
    # Buscamos el reembolso usando los primeros 8 caracteres del UUID
    reembolso = db.query(models.SolicitudReembolso).filter(
        models.SolicitudReembolso.uuid.startswith(folio_corto)
    ).first()

    if not reembolso:
        raise HTTPException(status_code=404, detail="Folio no encontrado")

    if not reembolso.link_expediente or not os.path.exists(reembolso.link_expediente):
        raise HTTPException(status_code=404, detail="Carpeta del expediente no encontrada")

    # Guardamos los nuevos archivos en la misma carpeta, agregando el prefijo "NUEVO_"
    archivos_guardados = 0
    for archivo in archivos:
        if archivo.filename:
            ruta_archivo = os.path.join(reembolso.link_expediente, f"NUEVO_{archivo.filename}")
            with open(ruta_archivo, "wb") as f:
                f.write(archivo.file.read())
            archivos_guardados += 1

    if archivos_guardados > 0:
        # Regresamos el estado a PENDIENTE para que RH lo vuelva a revisar
        reembolso.estatus = "PENDIENTE"
        reembolso.mensaje = "El trabajador envió documentación corregida/adicional."
        db.commit()

    return {"status": "success", "message": f"{archivos_guardados} archivos agregados al expediente"}


# --- ENDPOINT DE ESTADÍSTICAS (REPORTES) ---

@router.get("/estadisticas/dashboard")
def obtener_estadisticas_dashboard(
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(obtener_usuario_actual),
):
    """Genera los datos consolidados para las gráficas de reportes."""
    # Seguridad: Solo el administrador puede ver reportes globales
    if usuario_actual.rol != "admin_rh":
        raise HTTPException(
            status_code=403,
            detail="Privilegios insuficientes. Solo administradores pueden ver reportes.",
        )

    reembolsos = db.query(models.SolicitudReembolso).all()

    current_year = datetime.utcnow().year

    # Montos por mes (Enero a Diciembre del año actual)
    montos_por_mes = {i: 0.0 for i in range(1, 13)}

    # Conteo de estatus (Aprobado, Rechazado, Pendiente, etc.)
    estatus_counts = {}

    # Frecuencia de proveedores
    proveedores_counts = {}

    for r in reembolsos:
        # Agrupar estatus
        est = r.estatus.upper()
        estatus_counts[est] = estatus_counts.get(est, 0) + 1

        # Agrupar proveedores
        prov = r.nombre_proveedor.upper() if r.nombre_proveedor else "DESCONOCIDO"
        proveedores_counts[prov] = proveedores_counts.get(prov, 0) + 1

        # Sumar montos por mes (solo del año en curso)
        if r.fecha_recepcion and r.fecha_recepcion.year == current_year:
            mes = r.fecha_recepcion.month
            montos_por_mes[mes] += float(r.monto)

    # Ordenar proveedores para sacar el Top 5
    top_proveedores = sorted(proveedores_counts.items(), key=lambda item: item[1], reverse=True)[:5]

    return {
        "montos_por_mes": [montos_por_mes[i] for i in range(1, 13)],
        "estatus": estatus_counts,
        "top_proveedores": [{"nombre": k, "cantidad": v} for k, v in top_proveedores]
    }
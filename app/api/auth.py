from datetime import timedelta
from typing import Optional
import secrets
import string

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from fastapi.security import OAuth2PasswordRequestForm

from app.api import schemas
from app.core.security import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    verify_password,
    get_password_hash,
    obtener_usuario_actual,
)
from app.db import models
from app.db.database import SessionLocal
from app.services.notificador import NotificadorCorreo

router = APIRouter(prefix="/api", tags=["auth"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/login", response_model=schemas.Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # OAuth2 obliga a usar la palabra 'username' en el formulario, 
    # pero nosotros sabemos que ahí viene el correo.
    usuario = db.query(models.Usuario).filter(models.Usuario.correo == form_data.username).first()

    if not usuario or not verify_password(form_data.password, usuario.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Correo o contraseña incorrectos",
        )

    if usuario.rol not in ["admin_rh", "trabajador"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso restringido a personal autorizado",
        )

    expires_delta = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": usuario.correo, "rol": usuario.rol, "displayName": usuario.nombre_completo,},
        expires_delta=expires_delta,
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": int(expires_delta.total_seconds()),
        "displayName": usuario.nombre_completo,
    }

class CrearUsuarioReq(BaseModel):
    username: str
    displayName: str
    password: Optional[str] = None
    role: str
    isActive: bool
    dias_asignados: Optional[str] = "1,2,3,4,5,6,7"


class ActualizarUsuarioReq(BaseModel):
    username: str
    displayName: str
    password: Optional[str] = None
    role: str
    isActive: bool
    dias_asignados: Optional[str] = "1,2,3,4,5,6,7"


class RecuperarPasswordReq(BaseModel):
    username: str


class CambiarPasswordReq(BaseModel):
    password_actual: str
    password_nueva: str


@router.get("/usuarios")
def listar_usuarios(
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(obtener_usuario_actual),
):
    if usuario_actual.rol != "admin_rh":
        raise HTTPException(
            status_code=403,
            detail="Privilegios insuficientes. Solo los administradores pueden gestionar usuarios.",
        )

    """Devuelve la lista de usuarios formateada exactamente como Angular la espera."""
    usuarios = db.query(models.Usuario).all()
    resultado = []

    for u in usuarios:
        resultado.append(
            {
                "id": str(u.id),
                "username": u.correo,
                "displayName": u.nombre_completo,
                "role": "admin" if u.rol == "admin_rh" else "trabajador",
                "isActive": True,
                "createdAt": "2026-01-01T00:00:00",
                "updatedAt": "2026-01-01T00:00:00",
                "dias_asignados": u.dias_asignados,
            }
        )
    return resultado


@router.post("/usuarios")
def crear_usuario(
    data: CrearUsuarioReq,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(obtener_usuario_actual),
):
    if usuario_actual.rol != "admin_rh":
        raise HTTPException(
            status_code=403,
            detail="Privilegios insuficientes. Solo los administradores pueden gestionar usuarios.",
        )

    if db.query(models.Usuario).filter(models.Usuario.correo == data.username).first():
        return {"ok": False, "message": "El correo o matrícula ya está registrado"}

    alfabeto = string.ascii_letters + string.digits + "!@#$%^&*"
    password_temporal = "".join(secrets.choice(alfabeto) for _ in range(10))

    nuevo = models.Usuario(
        correo=data.username,
        nombre_completo=data.displayName,
        password_hash=get_password_hash(password_temporal),
        rol="admin_rh" if data.role == "admin" else "trabajador",
        dias_asignados=data.dias_asignados,
    )
    db.add(nuevo)
    db.commit()

    background_tasks.add_task(
        NotificadorCorreo.enviar_bienvenida_credenciales,
        correo_destino=data.username,
        nombre=data.displayName,
        password_temporal=password_temporal,
    )

    return {"ok": True, "message": "Usuario creado con éxito"}


@router.put("/usuarios/{user_id}")
def actualizar_usuario(
    user_id: int,
    data: ActualizarUsuarioReq,
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(obtener_usuario_actual),
):
    if usuario_actual.rol != "admin_rh":
        raise HTTPException(
            status_code=403,
            detail="Privilegios insuficientes. Solo los administradores pueden gestionar usuarios.",
        )

    u = db.query(models.Usuario).filter(models.Usuario.id == user_id).first()
    if not u:
        return {"ok": False, "message": "Usuario no encontrado"}

    u.correo = data.username
    u.nombre_completo = data.displayName
    if data.password:
        u.password_hash = get_password_hash(data.password)

    u.rol = "admin_rh" if data.role == "admin" else "trabajador"
    u.dias_asignados = data.dias_asignados

    db.commit()
    return {"ok": True, "message": "Usuario actualizado correctamente"}


@router.delete("/usuarios/{user_id}")
def eliminar_usuario(
    user_id: int,
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(obtener_usuario_actual),
):
    if usuario_actual.rol != "admin_rh":
        raise HTTPException(
            status_code=403,
            detail="Privilegios insuficientes. Solo los administradores pueden gestionar usuarios.",
        )

    u = db.query(models.Usuario).filter(models.Usuario.id == user_id).first()
    if u:
        db.delete(u)
        db.commit()
        return {"ok": True, "message": "Usuario eliminado"}
    return {"ok": False, "message": "Error al eliminar"}


@router.post("/recuperar-password")
def recuperar_password(
    data: RecuperarPasswordReq,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Genera una contraseña temporal y la envía por correo si el usuario existe."""
    usuario = db.query(models.Usuario).filter(models.Usuario.correo == data.username).first()

    mensaje_exito = {
        "ok": True,
        "message": "Si el correo está registrado, recibirás una nueva contraseña en breve.",
    }

    if not usuario:
        return mensaje_exito

    alfabeto = string.ascii_letters + string.digits + "!@#$%^&*"
    password_temporal = "".join(secrets.choice(alfabeto) for _ in range(10))

    usuario.password_hash = get_password_hash(password_temporal)
    db.commit()

    background_tasks.add_task(
        NotificadorCorreo.enviar_recuperacion_password,
        correo_destino=usuario.correo,
        password_temporal=password_temporal,
    )

    return mensaje_exito


@router.put("/usuarios/me/password")
def cambiar_password_propia(
    data: CambiarPasswordReq,
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(obtener_usuario_actual),
):
    """Permite a un usuario logueado cambiar su propia contraseña."""
    usuario = db.query(models.Usuario).filter(models.Usuario.id == usuario_actual.id).first()

    if not usuario:
        return {"ok": False, "message": "Usuario no encontrado."}

    if not verify_password(data.password_actual, usuario.password_hash):
        return {"ok": False, "message": "La contraseña actual es incorrecta."}

    usuario.password_hash = get_password_hash(data.password_nueva)
    db.commit()

    return {"ok": True, "message": "Contraseña actualizada exitosamente."}
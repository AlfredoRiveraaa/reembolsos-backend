from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from fastapi.security import OAuth2PasswordRequestForm

from app.api import schemas
from app.core.security import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    verify_password,
    get_password_hash,
    obtener_usuario_actual
)
from app.db import models
from app.db.database import SessionLocal

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

    if usuario.rol != "admin_rh":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso restringido a personal de RH",
        )

    expires_delta = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": usuario.correo, "rol": usuario.rol},
        expires_delta=expires_delta,
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": int(expires_delta.total_seconds()),
    }

@router.post("/usuarios", response_model=schemas.UsuarioResponse, status_code=201)
def crear_usuario(
    usuario_in: schemas.UsuarioCreate, 
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(obtener_usuario_actual)
):
    """
    Crea un nuevo usuario de RH. 
    Solo accesible para usuarios autenticados con rol admin_rh.
    """
    existente = db.query(models.Usuario).filter(models.Usuario.correo == usuario_in.correo).first()
    if existente:
        raise HTTPException(
            status_code=400, 
            detail="El correo ya está registrado"
        )

    nuevo_usuario = models.Usuario(
        correo=usuario_in.correo,
        nombre_completo=usuario_in.nombre_completo,
        password_hash=get_password_hash(usuario_in.password),
        rol=usuario_in.rol
    )

    try:
        db.add(nuevo_usuario)
        db.commit()
        db.refresh(nuevo_usuario)
        return nuevo_usuario
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al crear usuario: {str(e)}")
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime

class ReembolsoBase(BaseModel):
    uuid: str
    monto: float
    correo_solicitante: str
    nombre_proveedor: str
    estatus: str

class ReembolsoCreate(ReembolsoBase):
    forma_pago: Optional[str] = None
    rfc_emisor: Optional[str] = None
    fecha_factura: Optional[datetime] = None
    link_expediente: str

class ReembolsoResponse(ReembolsoBase):
    id: int
    fecha_recepcion: datetime
    forma_pago: Optional[str] = None
    rfc_emisor: Optional[str] = None
    fecha_factura: Optional[datetime] = None
    mensaje_rechazo: Optional[str] = None
    link_expediente: Optional[str] = None
    nombre_solicitante: Optional[str] = None
    fecha_resolucion: Optional[datetime] = None
    mensaje: Optional[str] = None

    class Config:
        from_attributes = True


class UsuarioCreate(BaseModel):
    correo: EmailStr
    nombre_completo: str
    password: str
    rol: str = "admin_rh"
    dias_asignados: Optional[str] = "1,2,3,4,5,6,7"


class UsuarioResponse(BaseModel):
    id: int
    correo: EmailStr
    nombre_completo: str
    rol: str
    dias_asignados: Optional[str] = None

    class Config:
        from_attributes = True


class Login(BaseModel):
    correo: str
    password: str


class UsuarioUpdate(BaseModel):
    nombre_completo: Optional[str] = None
    correo: Optional[EmailStr] = None
    rol: Optional[str] = None
    password: Optional[str] = None
    dias_asignados: Optional[str] = None


class Token(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
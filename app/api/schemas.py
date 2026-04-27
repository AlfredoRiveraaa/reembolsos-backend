from pydantic import BaseModel
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

    class Config:
        from_attributes = True


class UsuarioCreate(BaseModel):
    correo: str
    nombre_completo: str
    password: str
    rol: str = "admin_rh"


class UsuarioResponse(BaseModel):
    id: int
    correo: str
    nombre_completo: str
    rol: str

    class Config:
        from_attributes = True


class Login(BaseModel):
    correo: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
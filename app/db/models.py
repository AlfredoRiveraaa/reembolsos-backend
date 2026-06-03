from sqlalchemy import Column, Integer, String, Numeric, DateTime, Text, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db.database import Base

class SolicitudReembolso(Base):
    __tablename__ = "Solicitudes"

    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(String(50), unique=True, index=True, nullable=False)
    monto = Column(Numeric(10, 2), nullable=False)
    correo_solicitante = Column(String(100), nullable=False)
    nombre_solicitante = Column(String(200), nullable=True)
    nombre_proveedor = Column(String(200), nullable=False)
    estatus = Column(String(20), default="PENDIENTE", nullable=False)
    
    forma_pago = Column(String(50), nullable=True)
    rfc_emisor = Column(String(20), nullable=True)
    fecha_factura = Column(DateTime, nullable=True)
    mensaje = Column(Text, nullable=True)
    link_expediente = Column(Text, nullable=True)

    fecha_recepcion = Column(DateTime, default=datetime.now)
    
    revisado_por = Column(Integer, ForeignKey("Usuarios.id"), nullable=True)
    fecha_resolucion = Column(DateTime, nullable=True)

    revisor = relationship("Usuario", back_populates="reembolsos_revisados")


class Usuario(Base):
    __tablename__ = "Usuarios"

    id = Column(Integer, primary_key=True, index=True)
    correo = Column(String(150), unique=True, index=True, nullable=False)
    nombre_completo = Column(String(200), nullable=False)
    password_hash = Column(String(255), nullable=False)
    rol = Column(String(50), nullable=False, default="admin_rh")

    dias_asignados = Column(String(50), default="1,2,3,4,5,6,7")
    is_active = Column(Boolean, default=True)

    reembolsos_revisados = relationship("SolicitudReembolso", back_populates="revisor")
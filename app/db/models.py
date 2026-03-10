from sqlalchemy import Column, Integer, String, Numeric, DateTime, Text
from datetime import datetime
from app.db.database import Base

class SolicitudReembolso(Base):
    __tablename__ = "Solicitudes"

    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(String(50), unique=True, index=True, nullable=False)
    monto = Column(Numeric(10, 2), nullable=False)
    correo_solicitante = Column(String(100), nullable=False)
    nombre_proveedor = Column(String(200), nullable=False)
    estatus = Column(String(20), default="PENDIENTE", nullable=False)
    
    forma_pago = Column(String(50), nullable=True)
    rfc_emisor = Column(String(20), nullable=True)
    fecha_factura = Column(DateTime, nullable=True)
    mensaje_rechazo = Column(Text, nullable=True)
    link_expediente = Column(Text, nullable=True)

    fecha_recepcion = Column(DateTime, default=datetime.utcnow)
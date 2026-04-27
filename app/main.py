from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.database import engine
from app.db import models
from app.api.auth import router as auth_router
from app.api.routes import router as reembolsos_router

# Crear tablas en la BD
models.Base.metadata.create_all(bind=engine)

# Inicializar FastAPI
app = FastAPI(
    title="API Reembolsos DRH",
    version="1.0.0",
    description="Sistema de Gestión de Reembolsos con notificaciones automáticas"
)

# Middleware CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# RUTAS
# ==========================================

app.include_router(reembolsos_router)
app.include_router(auth_router)

# ==========================================
# ENDPOINTS - SALUD
# ==========================================

@app.get("/")
def read_root():
    """Endpoint de prueba - verifica que la API está activa."""
    return {
        "mensaje": "¡El cerebro de Python está vivo!",
        "versión": "1.0.0",
        "endpoints": {
            "reembolsos": "/api/reembolsos",
            "procesar_xml": "/api/reembolsos/procesar-xml",
            "actualizar_estatus": "/api/reembolsos/{id}/estatus"
        }
    }
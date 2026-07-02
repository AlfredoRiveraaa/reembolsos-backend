import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from app.db.database import engine
from app.db import models
from app.api.auth import router as auth_router
from app.api.routes import router as reembolsos_router

load_dotenv() # Asegurar que carga las variables de entorno

models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="API Reembolsos DRH",
    version="1.0.0",
    description="Sistema de Gestión de Reembolsos"
)

# Leer los orígenes permitidos desde el .env, separando por comas. 
# Si no hay, usa localhost por defecto.
origenes_permitidos = os.getenv(
    "ALLOWED_ORIGINS", 
    "http://localhost:4200"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origenes_permitidos, # Usar la lista dinámica
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(reembolsos_router)
app.include_router(auth_router)

@app.get("/")
def read_root():
    return {
        "mensaje": "¡El cerebro de Python está vivo!",
        "versión": "1.0.0"
    }
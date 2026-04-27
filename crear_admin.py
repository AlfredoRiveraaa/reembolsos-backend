import os

from dotenv import load_dotenv

from app.core.security import get_password_hash
from app.db import models
from app.db.database import SessionLocal, engine

load_dotenv()


def crear_admin_inicial():
    correo = os.getenv("ADMIN_RH_CORREO", "admin.rh@empresa.com")
    nombre = os.getenv("ADMIN_RH_NOMBRE", "Administrador RH")
    password = os.getenv("ADMIN_RH_PASSWORD", "Admin123!")
    rol = "admin_rh"

    # Asegura que la tabla exista antes del seeding.
    models.Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        existente = db.query(models.Usuario).filter(models.Usuario.correo == correo).first()
        if existente:
            print(f"Usuario ya existe: {correo}")
            return

        usuario = models.Usuario(
            correo=correo,
            nombre_completo=nombre,
            password_hash=get_password_hash(password),
            rol=rol,
        )

        db.add(usuario)
        db.commit()
        print(f"Usuario admin creado: {correo}")
        print("Recuerda cambiar ADMIN_RH_PASSWORD en .env en cuanto inicies sesion.")
    except Exception as e:
        db.rollback()
        print(f"Error creando admin: {str(e)}")
    finally:
        db.close()


if __name__ == "__main__":
    crear_admin_inicial()

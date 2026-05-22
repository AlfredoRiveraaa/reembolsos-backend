Para levantar el proyecto en tu compu, sigue estos pasos:

1. Base de Datos:

Abre el archivo database_setup.sql que está en el repo del backend y ejecútalo. Esto te creará la base de datos, las tablas y los usuarios de prueba.

2. Backend (FastAPI):

Clona el repo y muévete a la rama dev.

Crea tu entorno: python -m venv venv y actívalo.

Instala las librerías: pip install -r requirements.txt.

Copia el archivo .env.example, pégale el nombre .env y cambia la URL de la base de datos para que apunte a tu SQL Server local (pon tu nombre de servidor, usuario y contraseña de SQL). Te paso por privado la contraseña del correo para el robot.

Arranca el servidor: uvicorn app.main:app --reload.

3. Frontend (Angular):

Clona el repo, rama dev.

Instala paquetes: npm install.

Arranca Angular: ng serve -o.

Puedes iniciar sesión con el correo diego.admin@universidad.edu.mx. 

La contaseña para cualquiera de los usuarios es Password123

Cualquier duda me avisas
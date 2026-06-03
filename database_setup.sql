-- Ejecutar esto en la base de datos local (ejecutar en Microsft SQL Server Management Studio)
CREATE DATABASE ReembolsosDRH;
GO

USE ReembolsosDRH;
GO

-- 1. Crear Tabla Usuarios
CREATE TABLE Usuarios (
    id INT IDENTITY(1,1) PRIMARY KEY,
    correo VARCHAR(150) NOT NULL UNIQUE,
    nombre_completo VARCHAR(200) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    rol VARCHAR(50) NOT NULL DEFAULT 'admin_rh',
    dias_asignados VARCHAR(50) DEFAULT '1,2,3,4,5,6,7',
    is_active BIT DEFAULT 1
);
GO

-- 2. Crear Tabla Solicitudes
CREATE TABLE Solicitudes (
    id INT IDENTITY(1,1) PRIMARY KEY,
    uuid VARCHAR(50) NOT NULL UNIQUE,
    monto DECIMAL(10, 2) NOT NULL,
    correo_solicitante VARCHAR(100) NOT NULL,
    nombre_solicitante VARCHAR(200),
    nombre_proveedor VARCHAR(200) NOT NULL,
    estatus VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE',
    forma_pago VARCHAR(50),
    rfc_emisor VARCHAR(20),
    fecha_factura DATETIME,
    mensaje VARCHAR(MAX),
    link_expediente VARCHAR(MAX),
    fecha_recepcion DATETIME DEFAULT GETUTCDATE(),
    revisado_por INT FOREIGN KEY REFERENCES Usuarios(id),
    fecha_resolucion DATETIME
);
GO

-- 3. Insertar Usuarios de Prueba (La contraseña para todos es Password123)
INSERT INTO Usuarios (correo, nombre_completo, password_hash, rol, dias_asignados) VALUES
('alfredo.admin@universidad.edu.mx', 'Alfredo Rivera Admin', '$2b$12$nAo.VnlyUbFdIV5TvfIhs.7Our6FEBHXk6IqKEhT3IV0XXRsyDGl.', 'admin_rh', '1,2,3,4,5,6,7'),
('diego.admin@universidad.edu.mx', 'Diego Admin', '$2b$12$nAo.VnlyUbFdIV5TvfIhs.7Our6FEBHXk6IqKEhT3IV0XXRsyDGl.', 'admin_rh', '1,2,3,4,5,6,7'),
('maria.auxiliar@correo.buap.mx', 'María López', '$2b$12$nAo.VnlyUbFdIV5TvfIhs.7Our6FEBHXk6IqKEhT3IV0XXRsyDGl.', 'trabajador', '1,3'),
('pedro.auxiliar@correo.buap.mx', 'Pedro Gómez', '$2b$12$nAo.VnlyUbFdIV5TvfIhs.7Our6FEBHXk6IqKEhT3IV0XXRsyDGl.', 'trabajador', '2,4');
GO
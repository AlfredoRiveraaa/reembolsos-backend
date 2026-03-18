"""
Punto de entrada para el Robot de Correos

Este archivo se mantiene por compatibilidad.
El código real está en app/workers/robot_correos.py
"""

from app.workers.robot_correos import ejecutar_en_bucle

if __name__ == "__main__":
    # Ejecutar el robot cada 60 segundos
    ejecutar_en_bucle(intervalo_segundos=60)
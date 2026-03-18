#!/usr/bin/env python3
"""
Robot de Correos - Ejecutable Independiente
=============================================
Inicia el worker que procesa automáticamente correos de la bandeja de entrada.

Uso: python run_robot.py
     
Se ejecuta continuamente verificando nuevos correos cada 60 segundos.
"""

from app.workers.robot_correos import ejecutar_en_bucle

if __name__ == "__main__":
    print("=" * 60)
    print("ROBOT DE CORREOS - Sistema de Reembolsos")
    print("=" * 60)
    ejecutar_en_bucle(intervalo_segundos=60)

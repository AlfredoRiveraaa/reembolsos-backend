from app.services.extractor_xml import extraer_datos_factura

ruta_prueba = "SHGP-905- 8d08eaf0-3a76-457c-9da6-ee9bd498f55a.xml" 

print(f"Analizando el documento: {ruta_prueba}...\n")

resultado = extraer_datos_factura(ruta_prueba)

if resultado["status"] == "success":
    datos = resultado["datos"]
    print("¡Extracción Exitosa!")
    print(f"   - UUID:  {datos['uuid']}")
    print(f"   - RFC:   {datos['rfc_emisor']}")
    print(f"   - Monto: ${datos['monto_total']}")
else:
    print("Error en la extracción:")
    print(resultado["mensaje"])
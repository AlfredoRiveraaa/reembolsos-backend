import xml.etree.ElementTree as ET

def extraer_datos_factura(ruta_archivo_xml: str):
    """
    Lee un archivo XML (CFDI 4.0) y extrae el UUID, el RFC del Emisor, el Nombre del Emisor y el Monto Total.
    """
    try:
        arbol = ET.parse(ruta_archivo_xml)
        raiz = arbol.getroot()

        namespaces = {
            'cfdi': 'http://www.sat.gob.mx/cfd/4',
            'tfd': 'http://www.sat.gob.mx/TimbreFiscalDigital'
        }

        monto_total = float(raiz.attrib.get('Total', 0.0))

        nodo_emisor = raiz.find('cfdi:Emisor', namespaces)
        if nodo_emisor is not None:
            rfc_emisor = nodo_emisor.attrib.get('Rfc', "NO_ENCONTRADO")
            nombre_emisor = nodo_emisor.attrib.get('Nombre', "SIN_NOMBRE")
        else:
            rfc_emisor = "NO_ENCONTRADO"
            nombre_emisor = "SIN_NOMBRE"

        nodo_complemento = raiz.find('cfdi:Complemento', namespaces)
        uuid = "NO_ENCONTRADO"
        
        if nodo_complemento is not None:
            nodo_timbre = nodo_complemento.find('tfd:TimbreFiscalDigital', namespaces)
            if nodo_timbre is not None:
                uuid = nodo_timbre.attrib.get('UUID')

        return {
            "status": "success",
            "datos": {
                "uuid": uuid,
                "rfc_emisor": rfc_emisor,
                "nombre_emisor": nombre_emisor,
                "monto_total": monto_total
            }
        }

    except Exception as e:
        return {
            "status": "error",
            "mensaje": f"No se pudo procesar el XML: {str(e)}"
        }
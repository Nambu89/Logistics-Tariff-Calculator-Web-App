import pandas as pd
from typing import Dict

def cargar_pedido(ruta_archivo: str) -> pd.DataFrame:
    """
    Carga el archivo de pedido (Excel o CSV) y lo convierte en un DataFrame
    """
    if ruta_archivo.endswith('.csv'):
        return pd.read_csv(ruta_archivo)
    elif ruta_archivo.endswith(('.xls', '.xlsx')):
        return pd.read_excel(ruta_archivo)
    else:
        raise ValueError("Formato de archivo no soportado. Use CSV o Excel")
    
def buscar_productos(df_pedido: pd.DataFrame, df_productos: pd.DataFrame) -> pd.DataFrame:
    """
    Combina los datos del pedido con la información de los productos según el SKU
    """
    # Asegurarse de que los SKU coincidan en formato
    df_pedido['SKU'] = df_pedido['SKU'].str.upper()
    df_productos['SKU'] = df_productos['SKU'].str.upper()

    return pd.merge(df_pedido, df_productos, on='SKU', how='left')


def calcular_volumen_total(df_pedido_con_info: pd.DataFrame) -> float:
    """
    Calcula el volumen total del pedido basado en las dimensiones y cantidades de los productos.
    """
    return (df_pedido_con_info['ALTO EMBALAJE (MM)'] * df_pedido_con_info['ANCHO EMBALAJE (MM)'] * 
            df_pedido_con_info['FONDO EMBALAJE (MM)'] * df_pedido_con_info['CANTIDAD']).sum()

def calcular_num_palets(df_pedido_con_info: pd.DataFrame) -> int:
    """
    Calcula el número de palets necesarios basado en el volumen total.
    """
    volumen_total = calcular_volumen_total(df_pedido_con_info)
    volumen_palet = 1.2 * 0.8 * 2.16  # Volumen máximo de un palet (ancho * fondo * alto)
    return max(1, int(volumen_total / volumen_palet) + 1)

def procesar_pedido(ruta_archivo: str, df_productos: pd.DataFrame) -> Dict:
    """
    Procesa el pedido completo y devuelve la información necesaria para el cálculo de tarifas.
    """
    df_pedido = cargar_pedido(ruta_archivo)
    df_pedido_con_info = buscar_productos(df_pedido, df_productos)
    
    if df_pedido_con_info.empty:
        raise ValueError("No se encontraron productos en el archivo de pedido.")

    num_palets = calcular_num_palets(df_pedido_con_info)
    volumen_total = calcular_volumen_total(df_pedido_con_info)

    return {
        'Pedido': df_pedido_con_info,
        'Número de Palets': num_palets,
        'Volumen Total': volumen_total
    }
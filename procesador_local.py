from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
from io import BytesIO
import openpyxl
from openpyxl.styles import Font
import time
from openpyxl.utils import get_column_letter

# Configuración
SERVICE_ACCOUNT_FILE = 'credentials.json'
SCOPES = ['https://www.googleapis.com/auth/drive']
FOLDER_ID = '1pkTrRlS-WKJyR7_MVpU_emap2MaXgo_F'
CHECK_INTERVAL = 15  # Segundos entre verificaciones

# Inicialización
creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
drive_service = build('drive', 'v3', credentials=creds)

def parse_text_to_columns(text):
    """
    Procesa texto donde todo entre 'columna' y 'unidad' es el título,
    y la unidad va entre paréntesis
    """
    columns = []
    current_col = None
    words = text.split()
    i = 0
    
    while i < len(words):
        if words[i].lower() == 'columna' and i+1 < len(words):
            if current_col:  # Guardar columna anterior
                columns.append(current_col)
            
            # Capturar TODAS las palabras hasta encontrar 'unidad' o 'datos'
            name_parts = []
            i += 1  # Saltar 'columna'
            
            # Buscar siguiente palabra clave
            while i < len(words) and words[i].lower() not in ['unidad', 'datos']:
                name_parts.append(words[i])
                i += 1
            
            # Nueva columna
            current_col = {
                'name': ' '.join(name_parts),  # Título completo
                'unit': '',                   # Unidad (opcional)
                'values': []                  # Datos
            }
            
        elif current_col is not None:
            if words[i].lower() == 'unidad' and i+1 < len(words):
                current_col['unit'] = words[i+1]  # Guardar unidad
                i += 2
            elif words[i].lower() == 'datos':
                i += 1
                # Capturar todos los valores hasta próxima palabra clave
                while i < len(words) and words[i].lower() not in ['columna', 'unidad']:
                    current_col['values'].append(words[i])
                    i += 1
            else:
                i += 1
        else:
            i += 1
    
    if current_col:  # Añadir última columna
        columns.append(current_col)
    
    return columns

def get_unprocessed_files():
    """Obtiene archivos .txt no procesados"""
    query = f"'{FOLDER_ID}' in parents and mimeType='text/plain' and name contains 'datos_tabla_'"
    results = drive_service.files().list(q=query, fields="files(id,name)").execute()
    return results.get('files', [])

def mark_as_processed(file_id):
    """Renombra el archivo para marcarlo como procesado"""
    drive_service.files().update(
        fileId=file_id,
        body={'name': f"PROCESADO_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"},
        fields='name'
    ).execute()

def process_file(file_id):
    try:
        # Descargar archivo
        request = drive_service.files().get_media(fileId=file_id)
        fh = BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        
        done = False
        while not done:
            status, done = downloader.next_chunk()
        
        content = fh.getvalue().decode('utf-8').strip()
        print(f"\nContenido recibido:\n{content}\n")  # Debug
        
        # Extraer sección de datos
        data_section = content.split('---DATOS---')[1].strip() if '---DATOS---' in content else content
        
        # Procesar texto
        columns = parse_text_to_columns(data_section)
        
        if not columns:
            print("No se encontraron columnas válidas")
            return None

        # Crear Excel
        output = BytesIO()
        wb = openpyxl.Workbook()
        ws = wb.active
        
        # Escribir datos
        for col_idx, col_data in enumerate(columns, start=1):
            # Encabezado con unidad entre paréntesis
            header = f"{col_data['name']} ({col_data['unit']})" if col_data['unit'] else col_data['name']
            ws.cell(row=1, column=col_idx, value=header).font = Font(bold=False)
            
            # Valores (comenzando desde la fila 2)
            for row_idx, value in enumerate(col_data['values'], start=2):
                try:
                    # Intentar convertir a número
                    num_value = float(value) if '.' in value else int(value)
                    ws.cell(row=row_idx, column=col_idx, value=num_value)
                except ValueError:
                    ws.cell(row=row_idx, column=col_idx, value=value)
        
        # Ajustar columnas automáticamente
        for col in ws.columns:
            max_length = max(len(str(cell.value)) if cell.value else 0 for cell in col)
            ws.column_dimensions[get_column_letter(col[0].column)].width = max_length + 2
        
        # Guardar y subir
        wb.save(output)
        output.seek(0)
        
        excel_name = f"tabla_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        file_metadata = {
            'name': excel_name,
            'parents': [FOLDER_ID],
            'mimeType': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        }
        
        media = MediaIoBaseUpload(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            resumable=True
        )
        
        uploaded_file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id,name,webViewLink'
        ).execute()
        
        print(f"✅ Excel generado: {uploaded_file['name']}")
        return uploaded_file['name']
    
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        raise

def main_loop():
    """Bucle principal de monitoreo"""
    processed_files = set()
    
    while True:
        try:
            print(f"\n[{datetime.now()}] Buscando archivos nuevos...")
            files = get_unprocessed_files()
            
            for file in files:
                if file['id'] not in processed_files:
                    print(f"Procesando {file['name']}...")
                    try:
                        result = process_file(file['id'])
                        if result:
                            mark_as_processed(file['id'])
                            processed_files.add(file['id'])
                            print(f"✅ Tabla generada: {result}")
                    except Exception as e:
                        print(f"❌ Error procesando {file['name']}: {str(e)}")
            
            time.sleep(CHECK_INTERVAL)
            
        except KeyboardInterrupt:
            print("\nDeteniendo el monitor...")
            break
        except Exception as e:
            print(f"⚠️ Error en el bucle principal: {str(e)}")
            time.sleep(60)

if __name__ == '__main__':
    print(f"🚀 Iniciando procesador local a las {datetime.now()}...")
    main_loop()
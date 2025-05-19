# Sección de importaciones (al inicio del archivo)
from datetime import datetime  # <-- Esta es la importación crítica
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
from io import BytesIO, StringIO
import openpyxl
import time
import re

# Configuración
SERVICE_ACCOUNT_FILE = 'credentials.json'
SCOPES = ['https://www.googleapis.com/auth/drive']
FOLDER_ID = '1pkTrRlS-WKJyR7_MVpU_emap2MaXgo_F'
CHECK_INTERVAL = 15  # Segundos entre verificaciones

# Inicialización
creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
drive_service = build('drive', 'v3', credentials=creds)

def parse_compact_text(text):
    """Parsea el formato de línea única con comillas opcionales"""
    elements = []
    current = []
    in_quotes = False
    
    # Separar considerando comillas
    for part in text.split(' '):
        if not part:
            continue
        if part.startswith('"') and not in_quotes:
            in_quotes = True
            current.append(part[1:])
        elif part.endswith('"') and in_quotes:
            in_quotes = False
            current.append(part[:-1])
            elements.append(' '.join(current))
            current = []
        elif in_quotes:
            current.append(part)
        else:
            elements.append(part)
    
    # Procesar elementos
    columns = []
    current_col = {}
    i = 0
    n = len(elements)
    
    while i < n:
        if elements[i] == 'Columna' and i+1 < n:
            if current_col:
                columns.append(current_col)
            current_col = {
                'name': elements[i+1],
                'unit': '',
                'notes': '',
                'values': []
            }
            i += 2
        elif elements[i] == 'unidad' and i+1 < n and current_col:
            current_col['unit'] = elements[i+1]
            i += 2
        elif (elements[i] in ['apreciacion', 'apreciación']) and i+1 < n and current_col:
            current_col['notes'] = elements[i+1]
            i += 2
        elif elements[i] == 'datos' and current_col:
            i += 1
            while i < n and elements[i] not in ['Columna', 'unidad', 'apreciacion', 'apreciación']:
                current_col['values'].append(elements[i])
                i += 1
        else:
            i += 1
    
    if current_col:
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
        body={'name': f"PROCESADO_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"},  # Cambiado aquí
        fields='name'
    ).execute()

def process_file(file_id):
    """Descarga, procesa y sube el Excel"""
    # Descargar archivo
    request = drive_service.files().get_media(fileId=file_id)
    fh = BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    
    done = False
    while not done:
        status, done = downloader.next_chunk()
    
    content = fh.getvalue().decode('utf-8')
    
    # Extraer sección de datos
    if '---DATOS---' in content:
        # Formato multi-línea original
        data_match = re.search(r'---DATOS---\n(.+)', content, re.DOTALL)
        if not data_match:
            return None
        texto = data_match.group(1).strip()
    else:
        # Nuevo formato de línea única
        texto = content.split('\n', 1)[0].strip()  # Toma solo la primera línea

    # Parsear según el formato detectado
    if '\n' in texto:  # Formato multi-línea
        columns = []
        current_col = {}
        mode = None
        
        for line in texto.split('\n'):
            line = line.strip().lower()
            # ... (mantén el resto del parsing original)
    else:  # Formato de línea única
        columns = parse_compact_text(texto)
    
    # Procesamiento
    columns = []
    current_col = {}
    mode = None
    
    for line in texto.split('\n'):
        line = line.strip().lower()
        
        if line.startswith('Columna'):
            if current_col:
                columns.append(current_col)
            name = ' '.join(line.split()[1:])
            current_col = {
                'name': name,
                'unit': '',
                'notes': '',
                'values': []
            }
            mode = None
        
        elif line.startswith('unidad'):
            current_col['unit'] = ' '.join(line.split()[1:])
            mode = None
        
        elif line.startswith('apreciacion') or line.startswith('apreciación'):
            current_col['notes'] = ' '.join(line.split()[1:])
            mode = None
        
        elif line.startswith('datos'):
            mode = 'data'
        
        elif mode == 'data':
            values = [v for v in line.split() if v]
            current_col['values'].extend(values)
    
    if current_col:
        columns.append(current_col)
    
    # Crear Excel en memoria
    output = BytesIO()
    wb = openpyxl.Workbook()
    ws = wb.active
    
    # Escribir encabezados
    for i, col in enumerate(columns, 1):
        ws.cell(row=1, column=i, value=col['name']).font = openpyxl.styles.Font(bold=True)
        ws.cell(row=2, column=i, value=f"Unidad: {col['unit']}")
        ws.cell(row=3, column=i, value=f"Notas: {col['notes']}")
        
        # Escribir datos
        for row_idx, value in enumerate(col['values'], 4):
            try:
                num_value = float(value)
                ws.cell(row=row_idx, column=i, value=num_value)
            except ValueError:
                ws.cell(row=row_idx, column=i, value=value)
    
    # Ajustar columnas
    for col in ws.columns:
        max_length = 0
        column = col[0].column_letter
        for cell in col:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = (max_length + 2) * 1.2
        ws.column_dimensions[column].width = adjusted_width
    
    wb.save(output)
    output.seek(0)
    
    # Subir a Drive
    excel_name = f"tabla_procesada_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
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
    
    drive_service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id,name,webViewLink'
    ).execute()
    
    return excel_name

def main_loop():
    """Bucle principal de monitoreo"""
    processed_files = set()
    
    while True:
        try:
            print(f"\n[{datetime.now()}] Buscando archivos nuevos...")  # Cambiado aquí
            files = get_unprocessed_files()
            
            for file in files:
                if file['id'] not in processed_files:
                    print(f"Procesando {file['name']}...")
                    try:
                        result = process_file(file['id'])
                        if result:
                            mark_as_processed(file['id'])
                            processed_files.add(file['id'])
                            print(f"✅ Generado: {result}")
                    except Exception as e:
                        print(f"❌ Error procesando {file['name']}: {str(e)}")
            
            time.sleep(CHECK_INTERVAL)
            
        except KeyboardInterrupt:
            print("\nDeteniendo el monitor...")
            break
        except Exception as e:
            print(f"Error en el bucle principal: {str(e)}")
            time.sleep(60)

if __name__ == '__main__':
    print(f"Iniciando procesador local a las {datetime.now()}...")  # <-- Usa datetime.now()
    main_loop()
from datetime import datetime
import telebot
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from io import BytesIO

# Configuración
TELEGRAM_TOKEN = '7979624190:AAG4b20zfZysBcveOzaMvr2J715T904NOT8'
SERVICE_ACCOUNT_FILE = 'credentials.json'
SCOPES = ['https://www.googleapis.com/auth/drive.file']
FOLDER_ID = '1pkTrRlS-WKJyR7_MVpU_emap2MaXgo_F'

bot = telebot.TeleBot(TELEGRAM_TOKEN)
drive_service = build('drive', 'v3', credentials=service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES))

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"datos_tabla_{timestamp}.txt"
        
        # Determinar el formato del mensaje
        if any(keyword in message.text.lower() for keyword in ['\ncolumna', '\nunidad', '\napreciacion', '\ndatos']):
            # Formato multi-línea
            content = f"Usuario: {message.from_user.username or message.from_user.first_name}\n"
            content += f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            content += "---DATOS---\n"
            content += message.text
        else:
            # Formato de línea única
            content = message.text  # Guarda directamente la línea única
        
        # Subir a Drive
        file_metadata = {
            'name': filename,
            'parents': [FOLDER_ID],
            'mimeType': 'text/plain'
        }
        
        media = MediaIoBaseUpload(
            BytesIO(content.encode('utf-8')),
            mimetype='text/plain',
            resumable=True
        )
        
        file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()
        
        bot.reply_to(message, f"✅ Datos recibidos (ID: {file.get('id')}")
    
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {str(e)}")

if __name__ == '__main__':
    print("Bot de captura iniciado...")
    bot.polling()
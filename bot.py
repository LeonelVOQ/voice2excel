from datetime import datetime
import telebot
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from io import BytesIO
import os
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Configuración desde variables de entorno
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
SERVICE_ACCOUNT_FILE = os.getenv('GOOGLE_CREDENTIALS_FILE')
SCOPES = ['https://www.googleapis.com/auth/drive.file']
FOLDER_ID = os.getenv('DRIVE_FOLDER_ID')

# Verificar que las variables existan
if not all([TELEGRAM_TOKEN, SERVICE_ACCOUNT_FILE, FOLDER_ID]):
    raise ValueError("Faltan variables de entorno necesarias")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
drive_service = build('drive', 'v3', credentials=service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES))

# [El resto de tu código permanece igual...]
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"datos_tabla_{timestamp}.txt"
        
        if any(keyword in message.text.lower() for keyword in ['\ncolumna', '\nunidad', '\napreciacion', '\ndatos']):
            content = f"Usuario: {message.from_user.username or message.from_user.first_name}\n"
            content += f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            content += "---DATOS---\n"
            content += message.text
        else:
            content = message.text
        
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
import subprocess
import sys
from threading import Thread

def run_bot():
    subprocess.run([sys.executable, "bot.py"])

def run_processor():
    subprocess.run([sys.executable, "procesador_local.py"])

if __name__ == '__main__':
    bot_thread = Thread(target=run_bot)
    processor_thread = Thread(target=run_processor)
    
    bot_thread.start()
    processor_thread.start()
    
    bot_thread.join()
    processor_thread.join()
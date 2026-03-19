# ===== main.py =====
# Telegram bot для запуска Minecraft-ботов через Mineflayer

import os
import subprocess
import logging
import sys
from telegram import Update, ForceReply
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

# --- Настройки ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    print("❌ Ошибка: Не найден TELEGRAM_TOKEN в переменных окружения!")
    sys.exit(1)

# Включаем логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Хранилище состояний пользователей (в памяти)
user_data = {}

# --- Проверка доступности node ---
def check_node():
    """Проверяет, доступна ли команда node в системе."""
    try:
        result = subprocess.run(
            ['/usr/bin/env', 'node', '--version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            logger.info(f"Node.js установлен: {result.stdout.strip()}")
            return True
        else:
            logger.error("Node.js не отвечает корректно")
            return False
    except Exception as e:
        logger.error(f"Ошибка при проверке node: {e}")
        return False

# --- Команда /start ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_html(
        rf"👋 Привет, {user.mention_html()}! Я помогу тебе создать бота для Minecraft.",
        reply_markup=ForceReply(selective=True),
    )
    await update.message.reply_text(
        "Просто отправь мне команду /connect, и я начну."
    )

# --- Команда /connect ---
async def connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data[user_id] = {'step': 'waiting_for_ip'}
    await update.message.reply_text(
        "🌐 Отлично! Введи IP-адрес сервера (например, localhost или play.example.com):"
    )

# --- Команда /cancel ---
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in user_data:
        del user_data[user_id]
        await update.message.reply_text("❌ Процесс отменён.")
    else:
        await update.message.reply_text("❌ Нет активного процесса.")

# --- Обработка текстовых сообщений ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if user_id not in user_data:
        return  # игнорируем, если пользователь не в процессе

    step = user_data[user_id]['step']

    # Шаг 1: ввод IP
    if step == 'waiting_for_ip':
        user_data[user_id]['ip'] = text
        user_data[user_id]['step'] = 'waiting_for_port'
        await update.message.reply_text(
            "🔌 Введи порт (обычно 25565, просто нажми Enter, если не знаешь):",
            reply_markup=ForceReply(selective=True)
        )

    # Шаг 2: ввод порта
    elif step == 'waiting_for_port':
        port = text if text else '25565'
        user_data[user_id]['port'] = port
        user_data[user_id]['step'] = 'waiting_for_nick'
        await update.message.reply_text(
            "🧑 Введи никнейм для бота (например, MyBot):"
        )

    # Шаг 3: ввод ника и запуск бота
    elif step == 'waiting_for_nick':
        nick = text
        ip = user_data[user_id]['ip']
        port = user_data[user_id]['port']

        await update.message.reply_text(
            f"⚡ Запускаю бота с ником **{nick}** для подключения к **{ip}:{port}**... Это может занять несколько секунд."
        )

        # Проверяем наличие node перед запуском
        if not check_node():
            await update.message.reply_text(
                "❌ Ошибка: Node.js не найден на сервере. Сообщи администратору."
            )
            del user_data[user_id]
            return

        # Запускаем Node.js скрипт
        try:
            # Используем /usr/bin/env для поиска node в PATH
            process = subprocess.Popen(
                ['/usr/bin/env', 'node', 'minecraft_bot.js', ip, port, nick],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            # Ждём завершения (таймаут 5 секунд)
            try:
                stdout, stderr = process.communicate(timeout=5)
                if process.returncode == 0:
                    await update.message.reply_text(
                        f"✅ Бот **{nick}** успешно запущен и подключился к серверу!\n"
                        f"```\n{stdout}\n```"
                    )
                else:
                    await update.message.reply_text(
                        f"❌ Не удалось запустить бота. Ошибка:\n```\n{stderr}\n```"
                    )
            except subprocess.TimeoutExpired:
                # Если процесс не завершился за 5 секунд, значит он работает в фоне
                process.kill()  # убиваем, чтобы не завис
                await update.message.reply_text(
                    f"✅ Бот **{nick}** запущен и работает в фоновом режиме! Проверь сервер."
                )

        except Exception as e:
            logger.exception("Ошибка при запуске Node.js процесса")
            await update.message.reply_text(f"❌ Критическая ошибка: {e}")

        # Очищаем данные пользователя
        del user_data[user_id]

# --- Обработчик ошибок ---
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.warning(f"Update {update} вызвал ошибку {context.error}")

# --- Главная функция ---
def main():
    # Проверяем node при старте
    if not check_node():
        logger.error("Node.js не доступен! Бот не сможет запускать Minecraft-ботов.")
    else:
        logger.info("Node.js доступен, всё готово к работе.")

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("connect", connect))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    print("🤖 Telegram бот запущен и ждёт команды...")
    app.run_polling()

if __name__ == '__main__':
    main()

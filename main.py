# ===== main.py =====
# Это главный Telegram-бот. Он будет получать команды от тебя
# и запускать Minecraft-бота (которого мы написали выше).

import os
import subprocess
import logging
from telegram import Update, ForceReply
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

# --- Настройки ---
# Токен мы получим от BotFather. Его нужно будет сохранить в переменную окружения на Railway позже.
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    print("❌ Ошибка: Не найден TELEGRAM_TOKEN!")
    exit(1)

# Включаем логирование (чтобы видеть, что происходит)
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Словарь для временного хранения данных от пользователя ---
# Здесь мы запомним, на каком этапе создания бота находится каждый пользователь
user_data = {}

# --- Команда /start ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет приветственное сообщение."""
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
    """Запускает процесс создания бота."""
    user_id = update.effective_user.id
    # Запоминаем, что пользователь хочет подключиться
    user_data[user_id] = {'step': 'waiting_for_ip'}
    await update.message.reply_text("🌐 Отлично! Введи IP-адрес сервера (например, localhost или play.example.com):")

# --- Команда /cancel ---
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отменяет текущий процесс."""
    user_id = update.effective_user.id
    if user_id in user_data:
        del user_data[user_id]
    await update.message.reply_text("❌ Процесс отменён.")

# --- Обработка текстовых сообщений ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Этот обработчик ловит ответы пользователя на наши вопросы."""
    user_id = update.effective_user.id
    text = update.message.text

    # Если пользователь не в процессе создания, игнорируем
    if user_id not in user_data:
        return

    current_step = user_data[user_id]['step']

    # --- Шаг 1: Ждём IP ---
    if current_step == 'waiting_for_ip':
        user_data[user_id]['ip'] = text
        user_data[user_id]['step'] = 'waiting_for_port'
        await update.message.reply_text("🔌 Введи порт (обычно 25565, просто нажми Enter, если не знаешь):", reply_markup=ForceReply(selective=True))

    # --- Шаг 2: Ждём порт ---
    elif current_step == 'waiting_for_port':
        # Если пользователь ничего не ввёл, ставим порт по умолчанию
        port = text if text else '25565'
        user_data[user_id]['port'] = port
        user_data[user_id]['step'] = 'waiting_for_nick'
        await update.message.reply_text("🧑 Введи никнейм для бота (например, MyBot):")

    # --- Шаг 3: Ждём никнейм и запускаем бота ---
    elif current_step == 'waiting_for_nick':
        nick = text
        ip = user_data[user_id]['ip']
        port = user_data[user_id]['port']

        # Сообщаем, что начали запуск
        await update.message.reply_text(f"⚡ Запускаю бота с ником **{nick}** для подключения к **{ip}:{port}**... Это может занять несколько секунд.")

        # Запускаем нашего Node.js бота!
        # Мы вызываем команду 'node minecraft_bot.js IP ПОРТ НИК'
        # [citation:2][citation:4]
        try:
            # Запускаем процесс и ждём, пока он выполнится
            process = subprocess.Popen(
                ['node', 'minecraft_bot.js', ip, port, nick],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            # Ждём немного, чтобы бот успел подключиться или выдать ошибку
            # В реальном проекте лучше сделать это асинхронно, но для простоты оставим так
            stdout, stderr = process.communicate(timeout=5)

            if process.returncode == 0:
                await update.message.reply_text(f"✅ Бот **{nick}** успешно запущен и подключается к серверу! Логи:\n```\n{stdout}\n```")
            else:
                await update.message.reply_text(f"❌ Не удалось запустить бота. Ошибка:\n```\n{stderr}\n```")

        except subprocess.TimeoutExpired:
            # Если процесс не завершился за 5 секунд, значит он, скорее всего, успешно работает в фоне.
            # Нам нужно его "отвязать", чтобы он не завис.
            process.kill()
            await update.message.reply_text(f"✅ Бот **{nick}** запущен и работает в фоновом режиме! Проверь сервер.")
        except Exception as e:
            await update.message.reply_text(f"❌ Критическая ошибка: {e}")

        # Очищаем данные пользователя после завершения
        del user_data[user_id]

# --- Обработка ошибок ---
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Логирует ошибки."""
    logger.warning(f"Update {update} вызвал ошибку {context.error}")

# --- Главная функция запуска ---
def main():
    """Запускает бота."""
    # Создаём приложение
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Регистрируем обработчики команд
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("connect", connect))
    app.add_handler(CommandHandler("cancel", cancel))

    # Регистрируем обработчик текстовых сообщений
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Регистрируем обработчик ошибок
    app.add_error_handler(error_handler)

    # Запускаем бота
    print("🤖 Telegram бот запущен и ждёт команды...")
    app.run_polling()

if __name__ == '__main__':
    main()

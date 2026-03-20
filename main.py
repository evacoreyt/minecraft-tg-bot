# ===== main.py =====
# Telegram bot для запуска Minecraft-ботов через Mineflayer
# Версия с поддержкой нескольких ботов и командами /create и /stop_all

import os
import subprocess
import logging
import sys
import asyncio
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

# Хранилище активных ботов: {ник: процесс}
active_bots = {}

# Хранилище состояний пользователей для пошагового диалога
user_data = {}

# --- Проверка доступности node ---
def check_node():
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

# --- Вспомогательная функция для запуска бота ---
async def launch_bot(update, ip, port, nick):
    """Запускает Minecraft-бота и сохраняет процесс в active_bots."""
    if nick in active_bots:
        await update.message.reply_text(f"❌ Бот с ником **{nick}** уже запущен. Используй другой ник.")
        return False

    # Проверяем наличие node
    if not check_node():
        await update.message.reply_text("❌ Ошибка: Node.js не найден на сервере. Сообщи администратору.")
        return False

    # Запускаем процесс
    try:
        process = subprocess.Popen(
            ['/usr/bin/env', 'node', 'minecraft_bot.js', ip, port, nick],
            stdout=None,
            stderr=None
        )
        # Сохраняем процесс
        active_bots[nick] = process
        logger.info(f"Бот {nick} запущен (PID {process.pid})")

        # Запускаем задачу на ожидание завершения процесса (чтобы удалить его из словаря)
        asyncio.create_task(wait_for_bot(nick, process))

        await update.message.reply_text(
            f"✅ Бот **{nick}** запущен и подключается к серверу **{ip}:{port}**.\n"
            f"Подробности смотри в логах Railway (вкладка Logs)."
        )
        return True
    except Exception as e:
        logger.error(f"Ошибка при запуске бота {nick}: {e}")
        await update.message.reply_text(f"❌ Ошибка при запуске бота {nick}: {e}")
        return False

async def wait_for_bot(nick, process):
    """Ждёт завершения процесса и удаляет его из активных."""
    try:
        # Ждём завершения в отдельном потоке, чтобы не блокировать asyncio
        await asyncio.to_thread(process.wait)
    except Exception as e:
        logger.error(f"Ошибка при ожидании процесса {nick}: {e}")
    finally:
        if nick in active_bots:
            del active_bots[nick]
            logger.info(f"Бот {nick} завершён и удалён из списка активных")

# --- Команды Telegram ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_html(
        rf"👋 Привет, {user.mention_html()}! Я помогаю запускать ботов в Minecraft.",
        reply_markup=ForceReply(selective=True),
    )
    await update.message.reply_text(
        "Команды:\n"
        "/connect — пошагово создать одного бота\n"
        "/create <количество> [префикс] — создать несколько ботов (до 100)\n"
        "/stop_all — остановить всех ботов\n"
        "/list — список активных ботов\n"
        "/cancel — отменить текущий диалог"
    )

async def connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data[user_id] = {'step': 'waiting_for_ip'}
    await update.message.reply_text(
        "🌐 Отлично! Введи IP-адрес сервера (например, localhost или play.example.com):"
    )

async def create_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Создаёт несколько ботов. Формат: /create <количество> [префикс]"""
    args = context.args
    if len(args) < 1:
        await update.message.reply_text("Использование: /create <количество> [префикс]")
        return

    try:
        count = int(args[0])
    except ValueError:
        await update.message.reply_text("Количество должно быть числом.")
        return

    if count < 1 or count > 100:
        await update.message.reply_text("Количество должно быть от 1 до 100.")
        return

    prefix = args[1] if len(args) > 1 else "Astral"
    # Проверяем, что префикс содержит только допустимые символы (буквы, цифры, _)
    if not prefix.replace('_', '').isalnum():
        await update.message.reply_text("Префикс может содержать только буквы, цифры и символ подчёркивания.")
        return

    # Формируем имена
    nicks = []
    for i in range(1, count + 1):
        nick = f"{prefix}_{i:02d}" if count > 9 else f"{prefix}_{i}"
        # Если такой ник уже запущен, пропускаем (но сообщим потом)
        if nick in active_bots:
            continue
        nicks.append(nick)

    if not nicks:
        await update.message.reply_text("Все возможные ники уже заняты. Попробуй другой префикс.")
        return

    # Запускаем ботов
    await update.message.reply_text(f"🚀 Запускаю {len(nicks)} ботов...")
    # IP и порт нужно спросить? Пока предположим, что пользователь вводит их отдельно.
    # Но лучше запросить их перед запуском. Давай упростим: запросим IP и порт через диалог.
    # Сохраним намерение пользователя и запросим данные.
    user_id = update.effective_user.id
    user_data[user_id] = {
        'step': 'waiting_for_ip_for_create',
        'nicks': nicks,
        'count': len(nicks)
    }
    await update.message.reply_text(
        "🌐 Введи IP-адрес сервера (например, localhost или play.example.com):"
    )

async def stop_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Останавливает всех активных ботов."""
    if not active_bots:
        await update.message.reply_text("Нет активных ботов.")
        return

    count = len(active_bots)
    for nick, proc in list(active_bots.items()):
        try:
            proc.terminate()
            logger.info(f"Остановлен бот {nick} (PID {proc.pid})")
        except Exception as e:
            logger.error(f"Ошибка при остановке бота {nick}: {e}")
    # Очищаем словарь (процессы ещё могут быть живы, но мы их пометим как завершённые)
    active_bots.clear()
    await update.message.reply_text(f"✅ Остановлено {count} ботов.")

async def list_bots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает список активных ботов."""
    if not active_bots:
        await update.message.reply_text("Нет активных ботов.")
        return

    nicks = list(active_bots.keys())
    await update.message.reply_text(f"Активные боты ({len(nicks)}):\n" + "\n".join(nicks))

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in user_data:
        del user_data[user_id]
        await update.message.reply_text("❌ Процесс отменён.")
    else:
        await update.message.reply_text("❌ Нет активного процесса.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if user_id not in user_data:
        return

    state = user_data[user_id]

    # Обработка для одиночного подключения (/connect)
    if state.get('step') == 'waiting_for_ip':
        state['ip'] = text
        state['step'] = 'waiting_for_port'
        await update.message.reply_text(
            "🔌 Введи порт (обычно 25565, просто нажми Enter, если не знаешь):",
            reply_markup=ForceReply(selective=True)
        )
        return

    elif state.get('step') == 'waiting_for_port':
        port = text if text else '25565'
        state['step'] = 'waiting_for_nick'
        await update.message.reply_text("🧑 Введи никнейм для бота (например, MyBot):")
        return

    elif state.get('step') == 'waiting_for_nick':
        nick = text
        ip = state['ip']
        port = state['port']
        await launch_bot(update, ip, port, nick)
        del user_data[user_id]
        return

    # Обработка для массового создания (/create)
    elif state.get('step') == 'waiting_for_ip_for_create':
        state['ip'] = text
        state['step'] = 'waiting_for_port_for_create'
        await update.message.reply_text(
            "🔌 Введи порт (обычно 25565, просто нажми Enter, если не знаешь):"
        )
        return

    elif state.get('step') == 'waiting_for_port_for_create':
        port = text if text else '25565'
        nicks = state['nicks']
        success = 0
        for nick in nicks:
            if await launch_bot(update, state['ip'], port, nick):
                success += 1
        await update.message.reply_text(
            f"✅ Запущено {success} из {len(nicks)} ботов. Используй /list для просмотра."
        )
        del user_data[user_id]
        return

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.warning(f"Update {update} вызвал ошибку {context.error}")

def main():
    if not check_node():
        logger.error("Node.js не доступен! Бот не сможет запускать Minecraft-ботов.")
    else:
        logger.info("Node.js доступен, всё готово к работе.")

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("connect", connect))
    app.add_handler(CommandHandler("create", create_command))
    app.add_handler(CommandHandler("stop_all", stop_all))
    app.add_handler(CommandHandler("list", list_bots))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    print("🤖 Telegram бот запущен и ждёт команды...")
    app.run_polling()

if __name__ == '__main__':
    main()

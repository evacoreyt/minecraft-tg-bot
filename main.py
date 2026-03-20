# ===== main.py =====
# Telegram bot для запуска Minecraft-ботов через Mineflayer
# Поддержка нескольких ботов, прокси, команд /create, /stop, /stop_all, /list

import os
import subprocess
import logging
import sys
import asyncio
import random
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

# --- Загрузка прокси из файла ---
PROXY_LIST = []
try:
    with open("proxies.txt", "r") as f:
        PROXY_LIST = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    logger.info(f"Загружено {len(PROXY_LIST)} прокси из proxies.txt")
except FileNotFoundError:
    logger.warning("Файл proxies.txt не найден, работаем без прокси")
    PROXY_LIST = None

# Счётчик для циклической раздачи прокси
proxy_index = 0

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
    """Запускает Minecraft-бота, назначает прокси и сохраняет процесс."""
    if nick in active_bots:
        await update.message.reply_text(f"❌ Бот с ником **{nick}** уже запущен. Используй другой ник.")
        return False

    if not check_node():
        await update.message.reply_text("❌ Ошибка: Node.js не найден на сервере. Сообщи администратору.")
        return False

    # Выбираем прокси (если есть)
    proxy_url = None
    if PROXY_LIST:
        global proxy_index
        proxy_url = PROXY_LIST[proxy_index % len(PROXY_LIST)]
        proxy_index += 1
        logger.info(f"Боту {nick} назначен прокси {proxy_url}")
    else:
        logger.info(f"Бот {nick} запускается без прокси")

    # Формируем аргументы командной строки
    args = ['/usr/bin/env', 'node', 'minecraft_bot.js', ip, port, nick]
    if proxy_url:
        args.append(proxy_url)

    try:
        process = subprocess.Popen(
            args,
            stdout=None,
            stderr=None
        )
        active_bots[nick] = process
        asyncio.create_task(wait_for_bot(nick, process))

        await update.message.reply_text(
            f"✅ Бот **{nick}** запущен" + (f" через прокси {proxy_url}" if proxy_url else "") +
            f"\nПодключается к **{ip}:{port}**.\nПодробности в логах Railway."
        )
        return True
    except Exception as e:
        logger.error(f"Ошибка при запуске бота {nick}: {e}")
        await update.message.reply_text(f"❌ Ошибка при запуске бота {nick}: {e}")
        return False

async def wait_for_bot(nick, process):
    """Ждёт завершения процесса и удаляет бота из списка активных."""
    try:
        await asyncio.to_thread(process.wait)
    except Exception as e:
        logger.error(f"Ошибка при ожидании процесса {nick}: {e}")
    finally:
        if nick in active_bots:
            del active_bots[nick]
        logger.info(f"Бот {nick} завершён")

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
        "/stop <ник> — остановить конкретного бота\n"
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
    if not prefix.replace('_', '').isalnum():
        await update.message.reply_text("Префикс может содержать только буквы, цифры и символ подчёркивания.")
        return

    # Формируем имена
    nicks = []
    for i in range(1, count + 1):
        nick = f"{prefix}_{i:02d}" if count > 9 else f"{prefix}_{i}"
        if nick in active_bots:
            continue
        nicks.append(nick)

    if not nicks:
        await update.message.reply_text("Все возможные ники уже заняты. Попробуй другой префикс.")
        return

    user_id = update.effective_user.id
    user_data[user_id] = {
        'step': 'waiting_for_ip_for_create',
        'nicks': nicks,
        'count': len(nicks)
    }
    await update.message.reply_text(
        f"🚀 Запускаю {len(nicks)} ботов.\n🌐 Введи IP-адрес сервера:"
    )

async def stop_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Использование: /stop <ник>")
        return
    nick = context.args[0]
    if nick not in active_bots:
        await update.message.reply_text(f"Бот {nick} не найден в списке активных.")
        return
    proc = active_bots[nick]
    try:
        proc.terminate()
        await update.message.reply_text(f"✅ Отправлен сигнал остановки боту {nick}.")
    except Exception as e:
        logger.error(f"Ошибка при остановке {nick}: {e}")
        await update.message.reply_text(f"❌ Ошибка при остановке {nick}: {e}")

async def stop_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not active_bots:
        await update.message.reply_text("Нет активных ботов.")
        return
    count = len(active_bots)
    for nick, proc in list(active_bots.items()):
        try:
            proc.terminate()
            logger.info(f"Остановлен бот {nick}")
        except Exception as e:
            logger.error(f"Ошибка при остановке бота {nick}: {e}")
    active_bots.clear()
    await update.message.reply_text(f"✅ Остановлено {count} ботов.")

async def list_bots(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    app.add_handler(CommandHandler("stop", stop_bot))
    app.add_handler(CommandHandler("stop_all", stop_all))
    app.add_handler(CommandHandler("list", list_bots))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    print("🤖 Telegram бот запущен и ждёт команды...")
    app.run_polling()

if __name__ == '__main__':
    main()

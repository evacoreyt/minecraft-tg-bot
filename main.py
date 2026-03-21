# ===== main.py =====
import os
import subprocess
import logging
import sys
import asyncio
import time
from datetime import datetime, timedelta
from telegram import Update, ForceReply
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    print("❌ Ошибка: Не найден TELEGRAM_TOKEN!")
    sys.exit(1)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

active_bots = {}
user_data = {}
MAX_BOTS = 100
bot_launch_semaphore = asyncio.Semaphore(20)
_last_node_check = 0
_node_check_result = False

def check_node():
    global _last_node_check, _node_check_result
    now = time.time()
    if now - _last_node_check < 10:
        return _node_check_result
    try:
        result = subprocess.run(
            ['/usr/bin/env', 'node', '--version'],
            capture_output=True,
            text=True,
            timeout=15
        )
        if result.returncode == 0:
            logger.info(f"Node.js установлен: {result.stdout.strip()}")
            _node_check_result = True
        else:
            logger.error("Node.js не отвечает корректно")
            _node_check_result = False
    except subprocess.TimeoutExpired:
        logger.error("Проверка Node.js превысила таймаут 15 секунд")
        _node_check_result = False
    except Exception as e:
        logger.error(f"Ошибка при проверке node: {e}")
        _node_check_result = False
    _last_node_check = now
    return _node_check_result

async def launch_bot(update, ip, port, nick, ai_mode=False):
    async with bot_launch_semaphore:
        if nick in active_bots:
            await update.message.reply_text(f"❌ Бот **{nick}** уже запущен.")
            return False

        if not check_node():
            await update.message.reply_text("❌ Ошибка: Node.js не найден.")
            return False

        args = ['/usr/bin/env', 'node', 'minecraft_bot.js', ip, port, nick]
        if ai_mode:
            args.append('--ai')

        logger.info(f"Запускаю бота {nick} с параметрами {args}")

        try:
            process = subprocess.Popen(args, stdout=None, stderr=None)
            active_bots[nick] = {'process': process, 'start_time': time.time()}
            asyncio.create_task(wait_for_bot(nick, process))
            mode = "с ИИ" if ai_mode else "обычный"
            await update.message.reply_text(
                f"✅ Бот **{nick}** ({mode}) запущен.\n"
                f"Подключается к **{ip}:{port}**.\n"
                f"Подробности в логах Railway."
            )
            return True
        except Exception as e:
            logger.error(f"Ошибка при запуске бота {nick}: {e}")
            await update.message.reply_text(f"❌ Ошибка при запуске бота {nick}: {e}")
            return False

async def wait_for_bot(nick, process):
    try:
        returncode = await asyncio.to_thread(process.wait)
        logger.info(f"Бот {nick} завершился с кодом {returncode}")
    except Exception as e:
        logger.error(f"Ошибка при ожидании процесса {nick}: {e}")
    finally:
        if nick in active_bots:
            del active_bots[nick]
        logger.info(f"Бот {nick} удалён из списка активных")

# --- Команды ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_html(
        rf"👋 Привет, {user.mention_html()}! Я помогаю запускать ботов в Minecraft.",
        reply_markup=ForceReply(selective=True),
    )
    await update.message.reply_text(
        "Команды:\n"
        "/connect — пошагово создать одного бота\n"
        "/ai — запустить бота с ИИ (Gemini/OpenRouter/Ollama)\n"
        "/create <количество> [префикс] — создать несколько ботов\n"
        "/stop <ник> — остановить конкретного бота\n"
        "/stop_all — остановить всех ботов\n"
        "/list — список активных ботов\n"
        "/status — подробный статус\n"
        "/cancel — отменить текущий диалог"
    )

async def ai_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data[user_id] = {'step': 'waiting_for_ip', 'ai_mode': True}
    await update.message.reply_text(
        "🤖 Запуск бота с ИИ.\nВведи IP-адрес сервера:"
    )

async def connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data[user_id] = {'step': 'waiting_for_ip', 'ai_mode': False}
    await update.message.reply_text(
        "🌐 Введи IP-адрес сервера:"
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
    if count < 1 or count > 1000:
        await update.message.reply_text("Количество должно быть от 1 до 1000.")
        return
    prefix = args[1] if len(args) > 1 else "Astral"
    if not prefix.replace('_', '').isalnum():
        await update.message.reply_text("Префикс может содержать только буквы, цифры и подчёркивание.")
        return
    if len(active_bots) + count > MAX_BOTS:
        await update.message.reply_text(
            f"❌ Превышен лимит активных ботов ({MAX_BOTS}). Сейчас активно {len(active_bots)}.\n"
            "Используйте /stop_all или подождите, пока некоторые боты завершатся."
        )
        return
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
        'count': len(nicks),
        'ai_mode': False
    }
    await update.message.reply_text(
        f"🚀 Запускаю {len(nicks)} ботов.\n🌐 Введи IP-адрес сервера:"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    if user_id not in user_data:
        return
    state = user_data[user_id]
    step = state.get('step')
    ai_mode = state.get('ai_mode', False)

    if step == 'waiting_for_ip':
        state['ip'] = text
        state['step'] = 'waiting_for_port'
        await update.message.reply_text(
            "🔌 Введи порт (Enter = 25565):"
        )
        return

    elif step == 'waiting_for_port':
        port = text if text else '25565'
        state['port'] = port
        if 'nicks' in state:
            nicks = state['nicks']
            success = 0
            for nick in nicks:
                await update.message.reply_text(f"Запускаю бота {nick}...")
                if await launch_bot(update, state['ip'], port, nick, ai_mode=ai_mode):
                    success += 1
                await asyncio.sleep(5)
            await update.message.reply_text(
                f"✅ Запущено {success} из {len(nicks)} ботов."
            )
            del user_data[user_id]
        else:
            state['step'] = 'waiting_for_nick'
            await update.message.reply_text("🧑 Введи никнейм для бота:")
        return

    elif step == 'waiting_for_nick':
        nick = text
        ip = state['ip']
        port = state['port']
        await update.message.reply_text(f"Запускаю бота {nick}...")
        await launch_bot(update, ip, port, nick, ai_mode=ai_mode)
        del user_data[user_id]
        return

    elif step == 'waiting_for_ip_for_create':
        state['ip'] = text
        state['step'] = 'waiting_for_port_for_create'
        await update.message.reply_text(
            "🔌 Введи порт (Enter = 25565):"
        )
        return

    elif step == 'waiting_for_port_for_create':
        port = text if text else '25565'
        nicks = state['nicks']
        success = 0
        for nick in nicks:
            await update.message.reply_text(f"Запускаю бота {nick}...")
            if await launch_bot(update, state['ip'], port, nick, ai_mode=False):
                success += 1
            await asyncio.sleep(5)
        await update.message.reply_text(
            f"✅ Запущено {success} из {len(nicks)} ботов."
        )
        del user_data[user_id]
        return

# --- Остальные команды ---
async def stop_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Использование: /stop <ник>")
        return
    nick = context.args[0]
    if nick not in active_bots:
        await update.message.reply_text(f"Бот {nick} не найден.")
        return
    try:
        active_bots[nick]['process'].terminate()
        await update.message.reply_text(f"✅ Отправлен сигнал остановки боту {nick}.")
    except Exception as e:
        logger.error(f"Ошибка при остановке {nick}: {e}")
        await update.message.reply_text(f"❌ Ошибка при остановке {nick}: {e}")

async def stop_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not active_bots:
        await update.message.reply_text("Нет активных ботов.")
        return
    count = len(active_bots)
    for nick, data in list(active_bots.items()):
        try:
            data['process'].terminate()
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

async def status_bots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not active_bots:
        await update.message.reply_text("Нет активных ботов.")
        return
    lines = []
    for nick, data in active_bots.items():
        uptime_seconds = time.time() - data['start_time']
        uptime_str = str(timedelta(seconds=int(uptime_seconds)))
        lines.append(f"**{nick}** — PID {data['process'].pid}, работает {uptime_str}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in user_data:
        del user_data[user_id]
        await update.message.reply_text("❌ Процесс отменён.")
    else:
        await update.message.reply_text("❌ Нет активного процесса.")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.warning(f"Update {update} вызвал ошибку {context.error}")

def main():
    if not check_node():
        logger.error("Node.js не доступен!")
    else:
        logger.info("Node.js доступен.")

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("connect", connect))
    app.add_handler(CommandHandler("ai", ai_command))
    app.add_handler(CommandHandler("create", create_command))
    app.add_handler(CommandHandler("stop", stop_bot))
    app.add_handler(CommandHandler("stop_all", stop_all))
    app.add_handler(CommandHandler("list", list_bots))
    app.add_handler(CommandHandler("status", status_bots))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    print("🤖 Telegram бот запущен и ждёт команды...")
    app.run_polling()

if __name__ == '__main__':
    main()

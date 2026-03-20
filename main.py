# ===== main.py =====
# Telegram bot для запуска Minecraft-ботов через Mineflayer
# Упрощённая версия: боты используют прокси из proxies.txt напрямую.

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
    print("❌ Ошибка: Не найден TELEGRAM_TOKEN в переменных окружения!")
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

async def launch_bot(update, ip, port, nick):
    async with bot_launch_semaphore:
        if nick in active_bots:
            await update.message.reply_text(f"❌ Бот с ником **{nick}** уже запущен.")
            return False

        if not check_node():
            await update.message.reply_text("❌ Ошибка: Node.js не найден на сервере.")
            return False

        if not os.path.exists('proxies.txt'):
            await update.message.reply_text("⚠️ Внимание: файл proxies.txt не найден. Боты будут подключаться напрямую (риск блокировки).")

        args = ['/usr/bin/env', 'node', 'minecraft_bot.js', ip, port, nick]

        try:
            process = subprocess.Popen(args, stdout=None, stderr=None)
            active_bots[nick] = {'process': process, 'start_time': time.time()}
            asyncio.create_task(wait_for_bot(nick, process))
            await update.message.reply_text(
                f"✅ Бот **{nick}** запущен.\nПодключается к **{ip}:{port}**.\nПодробности в логах Railway."
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

# --- Команды Telegram (без изменений) ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_html(
        rf"👋 Привет, {user.mention_html()}! Я помогаю запускать ботов в Minecraft.",
        reply_markup=ForceReply(selective=True),
    )
    await update.message.reply_text(
        "Команды:\n"
        "/connect — пошагово создать одного бота\n"
        "/create <количество> [префикс] — создать несколько ботов (до 1000)\n"
        "/stop <ник> — остановить конкретного бота\n"
        "/stop_all — остановить всех ботов\n"
        "/list — список активных ботов (только ники)\n"
        "/status — подробный статус активных ботов\n"
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

    if count < 1 or count > 1000:
        await update.message.reply_text("Количество должно быть от 1 до 1000.")
        return

    prefix = args[1] if len(args) > 1 else "Astral"
    if not prefix.replace('_', '').isalnum():
        await update.message.reply_text("Префикс может содержать только буквы, цифры и символ подчёркивания.")
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
    proc = active_bots[nick]['process']
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
    for nick, data in list(active_bots.items()):
        try:
            data['process'].terminate()
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
            await asyncio.sleep(1)
        await update.message.reply_text(
            f"✅ Запущено {success} из {len(nicks)} ботов. Используй /list или /status для просмотра."
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
    app.add_handler(CommandHandler("status", status_bots))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    print("🤖 Telegram бот запущен и ждёт команды...")
    app.run_polling()

if __name__ == '__main__':
    main()

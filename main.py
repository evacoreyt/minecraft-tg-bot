# ===== main.py =====
# Telegram bot для запуска Minecraft-ботов через Mineflayer
# Автоматическая проверка и выбор лучших прокси по пингу

import os
import subprocess
import logging
import sys
import asyncio
import time
import socket
from datetime import datetime
from urllib.parse import urlparse
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

# Хранилище активных ботов: {ник: {'process': process, 'start_time': timestamp}}
active_bots = {}

# Хранилище состояний пользователей для пошагового диалога
user_data = {}

# Кэш для отсортированных прокси (обновляется раз в 5 минут)
proxy_cache = {
    'list': None,
    'last_update': 0
}
PROXY_CACHE_TTL = 300  # 5 минут

# --- Функция проверки пинга одного прокси ---
def ping_proxy(proxy_str, timeout=5):
    """
    Измеряет время TCP-соединения до прокси.
    Возвращает (proxy_str, ping_ms) или (proxy_str, None) при ошибке.
    """
    try:
        parsed = urlparse(proxy_str)
        if parsed.scheme != 'socks5':
            return (proxy_str, None)
        host = parsed.hostname
        port = parsed.port
        if not host or not port:
            return (proxy_str, None)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        start = time.time()
        sock.connect((host, port))
        ping = (time.time() - start) * 1000
        sock.close()
        return (proxy_str, ping)
    except Exception:
        return (proxy_str, None)

# --- Асинхронная проверка всех прокси ---
async def check_proxies(proxy_list, timeout=5, max_concurrent=50):
    """
    Асинхронно проверяет пинг списка прокси, возвращает список (proxy, ping)
    отсортированный по пингу (от меньшего к большему).
    """
    if not proxy_list:
        return []

    # Используем asyncio.to_thread для запуска синхронных измерений в пуле потоков
    semaphore = asyncio.Semaphore(max_concurrent)

    async def check_one(proxy):
        async with semaphore:
            return await asyncio.to_thread(ping_proxy, proxy, timeout)

    tasks = [check_one(p) for p in proxy_list]
    results = await asyncio.gather(*tasks)

    # Фильтруем только успешные
    good = [(p, ping) for p, ping in results if ping is not None]
    # Сортируем по пингу
    good.sort(key=lambda x: x[1])
    return good

# --- Загрузка прокси из файла ---
def load_proxies_from_file():
    proxies_file = "proxies.txt"
    try:
        with open(proxies_file, 'r') as f:
            proxies = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        logger.info(f"Загружено {len(proxies)} прокси из {proxies_file}")
        return proxies
    except FileNotFoundError:
        logger.warning(f"Файл {proxies_file} не найден. Боты будут работать без прокси.")
        return []

# --- Получение отсортированного списка прокси (с кэшированием) ---
async def get_sorted_proxies(force_refresh=False):
    now = time.time()
    if not force_refresh and proxy_cache['list'] is not None and (now - proxy_cache['last_update']) < PROXY_CACHE_TTL:
        logger.info("Использую кэшированный список прокси")
        return proxy_cache['list']

    proxies = load_proxies_from_file()
    if not proxies:
        proxy_cache['list'] = []
        proxy_cache['last_update'] = now
        return []

    logger.info(f"Проверяю {len(proxies)} прокси...")
    good_proxies = await check_proxies(proxies)
    logger.info(f"Рабочих прокси: {len(good_proxies)}")
    if good_proxies:
        # Выводим топ-5 для информации
        top5 = [f"{p[0]} ({p[1]:.0f}ms)" for p in good_proxies[:5]]
        logger.info(f"Лучшие прокси: {', '.join(top5)}")

    proxy_cache['list'] = good_proxies
    proxy_cache['last_update'] = now
    return good_proxies

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

# --- Вспомогательная функция для запуска бота (с прокси) ---
async def launch_bot(update, ip, port, nick, proxy_url=None):
    """Запускает Minecraft-бота с указанным прокси (или без)."""
    if nick in active_bots:
        await update.message.reply_text(f"❌ Бот с ником **{nick}** уже запущен. Используй другой ник.")
        return False

    if not check_node():
        await update.message.reply_text("❌ Ошибка: Node.js не найден на сервере. Сообщи администратору.")
        return False

    args = ['/usr/bin/env', 'node', 'minecraft_bot.js', ip, port, nick]
    if proxy_url:
        args.append(proxy_url)

    try:
        process = subprocess.Popen(
            args,
            stdout=None,
            stderr=None
        )
        active_bots[nick] = {
            'process': process,
            'start_time': time.time(),
            'proxy': proxy_url
        }
        asyncio.create_task(wait_for_bot(nick, process))

        msg = f"✅ Бот **{nick}** запущен.\nПодключается к **{ip}:{port}**."
        if proxy_url:
            msg += f"\nИспользует прокси: {proxy_url}"
        await update.message.reply_text(msg)
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
        "/list — список активных ботов (только ники)\n"
        "/status — подробный статус активных ботов\n"
        "/refresh — принудительно обновить список прокси\n"
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
        uptime_str = str(datetime.timedelta(seconds=int(uptime_seconds)))
        proxy_info = f" (прокси: {data.get('proxy', 'нет')})" if data.get('proxy') else ""
        lines.append(f"**{nick}** — PID {data['process'].pid}, работает {uptime_str}{proxy_info}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def refresh_proxies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Принудительно обновляет список прокси."""
    await update.message.reply_text("🔄 Обновляю список прокси... Это может занять до минуты.")
    await get_sorted_proxies(force_refresh=True)
    await update.message.reply_text(f"✅ Список обновлён. Рабочих прокси: {len(proxy_cache['list'])}")

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

    # --- Обработка одиночного бота (/connect) ---
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

        # Получаем отсортированные прокси
        sorted_proxies = await get_sorted_proxies()
        if sorted_proxies:
            best_proxy = sorted_proxies[0][0]  # берём первый (самый быстрый)
            await launch_bot(update, ip, port, nick, best_proxy)
        else:
            await launch_bot(update, ip, port, nick)  # без прокси
        del user_data[user_id]
        return

    # --- Обработка массового создания (/create) ---
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

        # Получаем отсортированные прокси
        sorted_proxies = await get_sorted_proxies()
        if not sorted_proxies:
            # Нет рабочих прокси – запускаем без прокси
            await update.message.reply_text("⚠️ Нет рабочих прокси. Боты будут подключаться без прокси.")
            success = 0
            for nick in nicks:
                if await launch_bot(update, state['ip'], port, nick):
                    success += 1
            await update.message.reply_text(
                f"✅ Запущено {success} из {len(nicks)} ботов. Используй /list или /status для просмотра."
            )
            del user_data[user_id]
            return

        # Отдаём лучшие прокси по очереди
        success = 0
        # Копируем список прокси, чтобы не менять оригинал
        proxies_iter = iter(sorted_proxies)
        for nick in nicks:
            try:
                proxy_url = next(proxies_iter)[0]
            except StopIteration:
                # Прокси закончились – начинаем сначала
                proxies_iter = iter(sorted_proxies)
                proxy_url = next(proxies_iter)[0]
            if await launch_bot(update, state['ip'], port, nick, proxy_url):
                success += 1

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
    app.add_handler(CommandHandler("refresh", refresh_proxies))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    print("🤖 Telegram бот запущен и ждёт команды...")
    app.run_polling()

if __name__ == '__main__':
    main()

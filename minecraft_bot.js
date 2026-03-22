// minecraft_bot.js – базовый бот с поддержкой прокси
const mineflayer = require('mineflayer');
const { SocksProxyAgent } = require('socks-proxy-agent');

// ---------- Настройки ----------
const RECONNECT_DELAY = 10000;      // 10 секунд между попытками
const MAX_RECONNECT_ATTEMPTS = 20;  // максимальное число попыток
const CONNECTION_TIMEOUT = 30000;   // 30 секунд таймаут подключения

let shouldReconnect = true;
let reconnectAttempts = 0;
let loginSuccess = false;
let currentBot = null;
let loginTimeout = null;

// Парсинг аргументов командной строки
const serverIp = process.argv[2];
const serverPort = parseInt(process.argv[3]) || 25565;
const botName = process.argv[4] || 'MineBot';
const proxyArg = process.argv.find(arg => arg.startsWith('--proxy='));
let proxyUrl = null;
if (proxyArg) {
    proxyUrl = proxyArg.split('=')[1];
}

// Создание бота с поддержкой прокси
function createBot() {
    console.log(`🤖 Попытка подключения бота ${botName} к ${serverIp}:${serverPort}...`);

    const options = {
        host: serverIp,
        port: serverPort,
        username: botName,
        auth: 'offline'
    };

    if (proxyUrl) {
        const agent = new SocksProxyAgent(proxyUrl);
        options.agent = agent;
        console.log(`🧦 Использую прокси: ${proxyUrl}`);
    }

    return mineflayer.createBot(options);
}

function attemptConnect() {
    if (!shouldReconnect) {
        console.log('🛑 Получен сигнал завершения, выходим без reconnect');
        process.exit(0);
    }

    reconnectAttempts++;
    if (reconnectAttempts > MAX_RECONNECT_ATTEMPTS) {
        console.log(`❌ Превышено максимальное число попыток (${MAX_RECONNECT_ATTEMPTS}). Завершение.`);
        process.exit(1);
    }

    const bot = createBot();

    if (!bot) {
        setTimeout(attemptConnect, RECONNECT_DELAY);
        return;
    }

    loginSuccess = false;
    currentBot = bot;

    loginTimeout = setTimeout(() => {
        if (!loginSuccess) {
            console.log('❌ Таймаут подключения (30 сек)');
            if (bot && bot._client) bot._client.end();
            process.exit(1);
        }
    }, CONNECTION_TIMEOUT);

    bot.on('login', () => {
        clearTimeout(loginTimeout);
        loginSuccess = true;
        reconnectAttempts = 0;
        console.log(`✅ Бот ${bot.username} успешно подключился к серверу!`);
    });

    bot.on('spawn', () => {
        console.log(`🌟 Бот ${bot.username} появился в мире!`);
        // Можно добавить приветственное сообщение (опционально)
        // bot.chat('Привет! Я бот-помощник.');
    });

    // Простая обработка сообщений (эхо) – если нужно, можно оставить или убрать
    bot.on('chat', (username, message) => {
        if (username === bot.username) return;
        console.log(`[CHAT] ${username}: ${message}`);
        // Убираем AI-ответы, можно оставить только логирование
        // bot.chat(`Привет, ${username}! Я слышал: ${message}`);
    });

    bot.on('kicked', (reason) => {
        console.log(`❌ Бот ${bot.username} был кикнут. Причина: ${reason}`);
        disconnectAndReconnect();
    });

    bot.on('error', (err) => {
        console.log(`⚠️ Ошибка у бота ${bot.username}:`, err.message);
        if (!loginSuccess) {
            disconnectAndReconnect();
        } else {
            console.log('❌ Критическая ошибка после входа, завершение');
            process.exit(1);
        }
    });

    bot.on('end', (reason) => {
        console.log(`🔌 Бот ${bot.username} отключился. Причина: ${reason || 'неизвестна'}`);
        if (!loginSuccess) {
            disconnectAndReconnect();
        } else {
            process.exit(0);
        }
    });
}

function disconnectAndReconnect() {
    if (currentBot && currentBot._client) currentBot._client.end();
    if (shouldReconnect) {
        setTimeout(attemptConnect, RECONNECT_DELAY);
    } else {
        process.exit(0);
    }
}

process.on('SIGTERM', () => {
    console.log('Получен SIGTERM, отключаю reconnect');
    shouldReconnect = false;
    if (currentBot && currentBot._client) currentBot._client.end();
    setTimeout(() => process.exit(0), 1000);
});

// Запуск
attemptConnect();

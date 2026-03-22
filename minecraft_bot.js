// minecraft_bot.js – базовый бот с поддержкой прокси, без автоматического переподключения
const mineflayer = require('mineflayer');
const { SocksProxyAgent } = require('socks-proxy-agent');

// ---------- Настройки ----------
const CONNECTION_TIMEOUT = 30000;   // 30 секунд таймаут подключения

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
    const bot = createBot();
    if (!bot) {
        console.error('❌ Не удалось создать бота');
        process.exit(1);
    }

    currentBot = bot;

    loginTimeout = setTimeout(() => {
        console.log('❌ Таймаут подключения (30 сек)');
        if (bot && bot._client) bot._client.end();
        process.exit(1);
    }, CONNECTION_TIMEOUT);

    bot.on('login', () => {
        clearTimeout(loginTimeout);
        console.log(`✅ Бот ${bot.username} успешно подключился к серверу!`);
    });

    bot.on('spawn', () => {
        console.log(`🌟 Бот ${bot.username} появился в мире!`);
    });

    bot.on('chat', (username, message) => {
        if (username === bot.username) return;
        console.log(`[CHAT] ${username}: ${message}`);
        // Можно добавить простой ответ, если нужно
        // bot.chat(`Привет, ${username}!`);
    });

    bot.on('kicked', (reason) => {
        console.log(`❌ Бот ${bot.username} был кикнут. Причина: ${reason}`);
        bot.quit();
        process.exit(0);
    });

    bot.on('error', (err) => {
        console.log(`⚠️ Ошибка у бота ${bot.username}:`, err.message);
        bot.quit();
        process.exit(1);
    });

    bot.on('end', (reason) => {
        console.log(`🔌 Бот ${bot.username} отключился. Причина: ${reason || 'неизвестна'}`);
        process.exit(0);
    });
}

process.on('SIGTERM', () => {
    console.log('Получен SIGTERM, завершаю бота...');
    if (currentBot && currentBot._client) currentBot._client.end();
    setTimeout(() => process.exit(0), 1000);
});

// Запуск
attemptConnect();

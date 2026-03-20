// minecraft_bot.js
const mineflayer = require('mineflayer');
const fs = require('fs');
const path = require('path');
let socksClient;
try {
    socksClient = require('socks').SocksClient;
} catch (e) {
    console.log('⚠️ Модуль socks не найден, прокси не будут работать');
    socksClient = null;
}

// ---------- Настройки ----------
const PROXY_FILE = path.join(__dirname, 'proxies.txt');      // ← читаем напрямую
const RECONNECT_DELAY = 5000;       // 5 секунд между попытками
const MAX_RECONNECT_ATTEMPTS = 20;  // максимальное число попыток
const CONNECTION_TIMEOUT = 30000;   // 30 секунд таймаут подключения

let proxyList = [];
let currentProxyIndex = 0;
let shouldReconnect = true;
let reconnectAttempts = 0;
let loginSuccess = false;
let currentBot = null;
let loginTimeout = null;

// Загружаем список прокси из файла proxies.txt
function loadProxyList() {
    try {
        const content = fs.readFileSync(PROXY_FILE, 'utf8');
        proxyList = content.split('\n')
            .map(line => line.trim())
            .filter(line => line && !line.startsWith('#'));
        console.log(`📄 Загружено ${proxyList.length} прокси из ${PROXY_FILE}`);
        if (proxyList.length === 0) {
            console.log('⚠️ Список прокси пуст, работаем без прокси');
        }
    } catch (err) {
        console.log(`⚠️ Не удалось прочитать ${PROXY_FILE}: ${err.message}. Работаем без прокси`);
        proxyList = [];
    }
}

// Выбирает следующий прокси (по кругу)
function getNextProxy() {
    if (proxyList.length === 0) return null;
    const proxy = proxyList[currentProxyIndex % proxyList.length];
    currentProxyIndex++;
    return proxy;
}

// Создаёт бота с указанным прокси
function createBotWithProxy(proxyUrl) {
    const serverIp = process.argv[2];
    const serverPort = parseInt(process.argv[3]) || 25565;
    const botName = process.argv[4] || 'MineBot';

    console.log(`🤖 Попытка подключения бота ${botName} к ${serverIp}:${serverPort}...`);

    let options = {
        host: serverIp,
        port: serverPort,
        username: botName,
        auth: 'offline'
    };

    if (proxyUrl && socksClient) {
        let proxyConfig;
        try {
            const parsed = new URL(proxyUrl);
            proxyConfig = {
                host: parsed.hostname,
                port: parseInt(parsed.port),
                type: 5,
                timeout: 30000
            };
            if (parsed.username && parsed.password) {
                proxyConfig.userId = parsed.username;
                proxyConfig.password = parsed.password;
            }
        } catch (e) {
            console.log(`❌ Неверный формат прокси: ${proxyUrl}`);
            return null;
        }
        console.log(`🌐 Использую прокси ${proxyConfig.host}:${proxyConfig.port}`);

        options.connect = (client) => {
            socksClient.createConnection({
                proxy: proxyConfig,
                command: 'connect',
                destination: {
                    host: serverIp,
                    port: serverPort
                },
                timeout: 30000
            }, (err, info) => {
                if (err) {
                    console.log(`❌ Ошибка прокси: ${err.message}`);
                    client.emit('error', err);
                    return;
                }
                client.setSocket(info.socket);
                client.emit('connect');
            });
        };
    } else if (proxyUrl && !socksClient) {
        console.log('❌ Модуль socks не загружен, прокси не будет использован');
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

    const proxy = getNextProxy();
    const bot = createBotWithProxy(proxy);

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
        console.log(`🔌 Бот ${bot.username} отключился от сервера. Причина: ${reason || 'неизвестна'}`);
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

loadProxyList();
attemptConnect();

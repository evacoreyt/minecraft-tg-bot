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
const PROXY_FILE = path.join(__dirname, 'proxies.txt');
const RECONNECT_DELAY = 10000;   // 10 секунд между попытками
const MAX_RECONNECT_ATTEMPTS = 50; // максимальное число попыток

let proxyList = [];
let currentProxyIndex = 0;
let reconnectAttempts = 0;
let shouldReconnect = true;  // флаг, который сбрасывается при получении SIGTERM
let isConnected = false;      // чтобы не переподключаться, если уже успешно зашли

// Загружаем список прокси из файла
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
        let proxy;
        try {
            const parsed = new URL(proxyUrl);
            proxy = {
                host: parsed.hostname,
                port: parseInt(parsed.port),
                type: 5
            };
            if (parsed.username && parsed.password) {
                proxy.userId = parsed.username;
                proxy.password = parsed.password;
            }
        } catch (e) {
            console.log(`❌ Неверный формат прокси: ${proxyUrl}`);
            return null;
        }
        console.log(`🌐 Использую прокси ${proxy.host}:${proxy.port}`);

        options.connect = (client) => {
            socksClient.createConnection({
                proxy: proxy,
                command: 'connect',
                destination: {
                    host: serverIp,
                    port: serverPort
                }
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

function startBot() {
    reconnectAttempts = 0;
    tryConnect();
}

function tryConnect() {
    if (!shouldReconnect) {
        console.log('🛑 Получен сигнал завершения, выходим без reconnect');
        process.exit(0);
    }

    reconnectAttempts++;
    if (reconnectAttempts > MAX_RECONNECT_ATTEMPTS) {
        console.log(`❌ Превышено максимальное число попыток (${MAX_RECONNECT_ATTEMPTS}). Завершение.`);
        process.exit(1);
    }

    const proxy = proxyList.length ? getNextProxy() : null;
    const bot = createBotWithProxy(proxy);

    if (!bot) {
        // Ошибка создания бота – сразу следующая попытка
        setTimeout(tryConnect, RECONNECT_DELAY);
        return;
    }

    let alreadyConnected = false;

    bot.on('login', () => {
        isConnected = true;
        alreadyConnected = true;
        console.log(`✅ Бот ${bot.username} успешно подключился к серверу!`);
        // Сбрасываем счётчик попыток при успехе
        reconnectAttempts = 0;
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
        // Некоторые ошибки (например, ECONNREFUSED) не требуют reconnect, если они случились до логина
        if (!alreadyConnected) {
            disconnectAndReconnect();
        } else {
            // Если уже был подключён, а потом ошибка – возможно, сервер упал, переподключаемся
            disconnectAndReconnect();
        }
    });

    bot.on('end', (reason) => {
        console.log(`🔌 Бот ${bot.username} отключился от сервера. Причина: ${reason || 'неизвестна'}`);
        if (alreadyConnected) {
            // Если бот уже был в игре, значит он вышел нормально (или его кикнуло, но это обработано выше)
            // В любом случае, если reconnect разрешён, пробуем переподключиться
            if (shouldReconnect) {
                disconnectAndReconnect();
            } else {
                process.exit(0);
            }
        } else {
            // Не успел подключиться – пробуем другой прокси
            disconnectAndReconnect();
        }
    });

    function disconnectAndReconnect() {
        if (bot._client) bot._client.end();
        if (shouldReconnect) {
            setTimeout(tryConnect, RECONNECT_DELAY);
        } else {
            process.exit(0);
        }
    }
}

// Обработка сигнала завершения (SIGTERM) – приходит от Python при остановке бота
process.on('SIGTERM', () => {
    console.log('Получен SIGTERM, отключаю reconnect');
    shouldReconnect = false;
    // Можно не выходить сразу, дадим время завершиться
    setTimeout(() => process.exit(0), 1000);
});

// Загружаем прокси и стартуем
loadProxyList();
startBot();

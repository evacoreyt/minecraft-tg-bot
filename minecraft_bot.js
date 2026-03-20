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
const MAX_RECONNECT_ATTEMPTS = 30; // сколько раз перебирать прокси

let proxyList = [];         // массив строк socks5://...
let currentProxyIndex = 0;  // индекс текущего прокси

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

// Выбирает следующий прокси (по кругу) и увеличивает индекс
function getNextProxy() {
    if (proxyList.length === 0) return null;
    const proxy = proxyList[currentProxyIndex % proxyList.length];
    currentProxyIndex++;
    return proxy;
}

// Создаёт бота с указанным прокси (или без)
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

// Основная функция с reconnect-логикой
function startBot() {
    let attemptCount = 0;

    function tryConnect() {
        attemptCount++;
        const proxy = proxyList.length ? getNextProxy() : null;
        const bot = createBotWithProxy(proxy);

        if (!bot) {
            // Ошибка создания бота (например, неверный прокси) – сразу следующая попытка
            if (attemptCount >= MAX_RECONNECT_ATTEMPTS) {
                console.log(`❌ Превышено максимальное число попыток (${MAX_RECONNECT_ATTEMPTS}). Завершение.`);
                process.exit(1);
            }
            setTimeout(tryConnect, 2000);
            return;
        }

        let isConnected = false;

        bot.on('login', () => {
            isConnected = true;
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
            disconnectAndReconnect();
        });

        bot.on('end', (reason) => {
            if (!isConnected) {
                console.log(`🔌 Бот ${bot.username} отключился до завершения подключения. Причина: ${reason || 'неизвестна'}`);
                disconnectAndReconnect();
            } else {
                console.log(`🔌 Бот ${bot.username} отключился от сервера. Причина: ${reason || 'неизвестна'}`);
                // Если уже был подключён, можно завершить процесс, но можно и переподключиться
                // Для стабильности лучше завершить, чтобы Python-бот не держал процесс
                process.exit(0);
            }
        });

        function disconnectAndReconnect() {
            if (bot._client) bot._client.end();
            if (attemptCount >= MAX_RECONNECT_ATTEMPTS) {
                console.log(`❌ Превышено максимальное число попыток (${MAX_RECONNECT_ATTEMPTS}). Завершение.`);
                process.exit(1);
            }
            setTimeout(tryConnect, 3000); // пауза перед следующей попыткой
        }
    }

    tryConnect();
}

// Загружаем прокси и стартуем
loadProxyList();
startBot();

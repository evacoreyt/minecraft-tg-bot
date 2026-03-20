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

const PROXY_FILE = path.join(__dirname, 'proxies.txt');
const RECONNECT_DELAY = 10000; // 10 секунд

let proxyList = [];
let currentProxyIndex = 0;
let shouldReconnect = true;     // флаг, отключаемый после успешного входа
let isConnected = false;

function loadProxyList() {
    try {
        const content = fs.readFileSync(PROXY_FILE, 'utf8');
        proxyList = content.split('\n')
            .map(line => line.trim())
            .filter(line => line && !line.startsWith('#'));
        console.log(`📄 Загружено ${proxyList.length} прокси из ${PROXY_FILE}`);
    } catch (err) {
        console.log(`⚠️ Не удалось прочитать ${PROXY_FILE}: ${err.message}`);
        proxyList = [];
    }
}

function getNextProxy() {
    if (proxyList.length === 0) return null;
    const proxy = proxyList[currentProxyIndex % proxyList.length];
    currentProxyIndex++;
    return proxy;
}

function createBot() {
    const serverIp = process.argv[2];
    const serverPort = parseInt(process.argv[3]) || 25565;
    const botName = process.argv[4] || 'MineBot';

    if (!serverIp) {
        console.log('❌ Ошибка: Не указан IP сервера!');
        process.exit(1);
    }

    console.log(`🤖 Попытка подключения бота ${botName} к ${serverIp}:${serverPort}...`);

    let options = {
        host: serverIp,
        port: serverPort,
        username: botName,
        auth: 'offline'
    };

    const proxy = getNextProxy();
    if (proxy && socksClient) {
        let proxyConfig;
        try {
            const parsed = new URL(proxy);
            proxyConfig = {
                host: parsed.hostname,
                port: parseInt(parsed.port),
                type: 5
            };
            if (parsed.username && parsed.password) {
                proxyConfig.userId = parsed.username;
                proxyConfig.password = parsed.password;
            }
        } catch (e) {
            console.log(`❌ Неверный формат прокси: ${proxy}`);
            setTimeout(() => attemptConnect(), RECONNECT_DELAY);
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
    } else if (proxy && !socksClient) {
        console.log('❌ Модуль socks не загружен, прокси не будет использован');
    }

    const bot = mineflayer.createBot(options);

    let loginSuccess = false;

    bot.on('login', () => {
        loginSuccess = true;
        isConnected = true;
        shouldReconnect = false; // успешно зашли – больше не переподключаемся
        console.log(`✅ Бот ${botName} успешно подключился к серверу!`);
    });

    bot.on('spawn', () => {
        console.log(`🌟 Бот ${botName} появился в мире!`);
    });

    bot.on('kicked', (reason) => {
        console.log(`❌ Бот ${botName} был кикнут. Причина: ${reason}`);
        if (!loginSuccess && shouldReconnect) {
            setTimeout(() => attemptConnect(), RECONNECT_DELAY);
        } else {
            process.exit(1);
        }
    });

    bot.on('error', (err) => {
        console.log(`⚠️ Ошибка у бота ${botName}:`, err.message);
        if (!loginSuccess && shouldReconnect) {
            setTimeout(() => attemptConnect(), RECONNECT_DELAY);
        } else {
            process.exit(1);
        }
    });

    bot.on('end', (reason) => {
        console.log(`🔌 Бот ${botName} отключился от сервера. Причина: ${reason || 'неизвестна'}`);
        if (!loginSuccess && shouldReconnect) {
            setTimeout(() => attemptConnect(), RECONNECT_DELAY);
        } else {
            process.exit(0);
        }
    });

    return bot;
}

let currentBot = null;

function attemptConnect() {
    if (currentBot) {
        if (currentBot._client) currentBot._client.end();
    }
    currentBot = createBot();
}

process.on('SIGTERM', () => {
    console.log('Получен SIGTERM, завершаюсь');
    shouldReconnect = false;
    if (currentBot && currentBot._client) currentBot._client.end();
    setTimeout(() => process.exit(0), 1000);
});

loadProxyList();
attemptConnect();

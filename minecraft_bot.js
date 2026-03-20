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
let proxyList = [];
let currentProxyIndex = 0;

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
function getProxy() {
    if (proxyList.length === 0) return null;
    const proxy = proxyList[currentProxyIndex % proxyList.length];
    currentProxyIndex++;
    return proxy;
}

// Создаёт бота
function createBot() {
    const serverIp = process.argv[2];
    const serverPort = parseInt(process.argv[3]) || 25565;
    const botName = process.argv[4] || 'MineBot';

    if (!serverIp) {
        console.log('❌ Ошибка: Не указан IP сервера!');
        process.exit(1);
    }

    console.log(`🤖 Запускаю бота ${botName} для подключения к ${serverIp}:${serverPort}...`);

    let options = {
        host: serverIp,
        port: serverPort,
        username: botName,
        auth: 'offline'
    };

    const proxy = getProxy();
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
            process.exit(1);
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

    bot.on('login', () => {
        console.log(`✅ Бот ${botName} успешно подключился к серверу!`);
    });

    bot.on('spawn', () => {
        console.log(`🌟 Бот ${botName} появился в мире!`);
    });

    bot.on('kicked', (reason) => {
        console.log(`❌ Бот ${botName} был кикнут. Причина: ${reason}`);
        process.exit(1);
    });

    bot.on('error', (err) => {
        console.log(`⚠️ Ошибка у бота ${botName}:`, err.message);
        process.exit(1);
    });

    bot.on('end', (reason) => {
        console.log(`🔌 Бот ${botName} отключился от сервера. Причина: ${reason || 'неизвестна'}`);
        process.exit(0);
    });
}

// Загружаем прокси и запускаем
loadProxyList();
createBot();

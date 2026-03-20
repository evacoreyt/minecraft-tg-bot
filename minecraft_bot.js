// minecraft_bot.js
const mineflayer = require('mineflayer');
let socksClient;
try {
    socksClient = require('socks').SocksClient;
} catch (e) {
    console.log('⚠️ Модуль socks не найден, прокси не будут работать');
    socksClient = null;
}

const serverIp = process.argv[2];
const serverPort = parseInt(process.argv[3]) || 25565;
const botName = process.argv[4] || 'MineBot';
const proxyArg = process.argv[5];  // пятый аргумент – прокси (если передан)

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

// Если прокси передан и модуль socks доступен
if (proxyArg && socksClient) {
    let proxyConfig;
    try {
        const parsed = new URL(proxyArg);
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
        console.log(`❌ Неверный формат прокси: ${proxyArg}`);
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
} else if (proxyArg && !socksClient) {
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

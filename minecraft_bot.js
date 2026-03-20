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
const proxyArg = process.argv[5];

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

if (proxyArg && socksClient) {
    let proxyUrl;
    try {
        proxyUrl = new URL(proxyArg);
    } catch (e) {
        console.log(`❌ Неверный формат прокси: ${proxyArg}`);
        process.exit(1);
    }

    const proxy = {
        host: proxyUrl.hostname,
        port: parseInt(proxyUrl.port),
        type: 5
    };
    if (proxyUrl.username && proxyUrl.password) {
        proxy.userId = proxyUrl.username;
        proxy.password = proxyUrl.password;
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
    if (err.code === 'ECONNREFUSED') {
        console.log(`❌ Не удалось подключиться к серверу ${serverIp}:${serverPort}. Проверьте IP и порт.`);
    }
    if (err.code === 'ETIMEDOUT') {
        console.log(`❌ Таймаут подключения к серверу через прокси. Прокси может быть нерабочим.`);
    }
    process.exit(1);
});

bot.on('end', (reason) => {
    console.log(`🔌 Бот ${botName} отключился от сервера. Причина: ${reason || 'неизвестна'}`);
    process.exit(0);
});

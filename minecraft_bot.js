// ===== minecraft_bot.js =====
// Minecraft-бот с автоопределением версии и поддержкой SOCKS5-прокси

const mineflayer = require('mineflayer');

// Получаем параметры из командной строки
const serverIp = process.argv[2];
const serverPort = parseInt(process.argv[3]) || 25565;
const botName = process.argv[4] || 'MineBot';
const proxyArg = process.argv[5]; // пятый аргумент – прокси

if (!serverIp) {
    console.log('❌ Ошибка: Не указан IP сервера!');
    process.exit(1);
}

console.log(`🤖 Запускаю бота ${botName} для подключения к ${serverIp}:${serverPort}...`);

let options = {
    host: serverIp,
    port: serverPort,
    username: botName,
    auth: 'offline' // для пиратских серверов
};

// Подключаем прокси, если передан
if (proxyArg) {
    const socks = require('socks');
    const proxyUrl = new URL(proxyArg);
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
        socks.createConnection({
            proxy: proxy,
            command: 'connect',
            destination: {
                host: serverIp,
                port: serverPort
            }
        }, (err, info) => {
            if (err) {
                console.log('❌ Ошибка прокси:', err);
                return;
            }
            client.setSocket(info.socket);
            client.emit('connect');
        });
    };
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
});

bot.on('end', (reason) => {
    console.log(`🔌 Бот ${botName} отключился от сервера. Причина: ${reason || 'неизвестна'}`);
    process.exit(0);
});

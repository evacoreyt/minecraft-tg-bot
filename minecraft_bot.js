// ===== minecraft_bot.js =====
// Minecraft-бот с автоопределением версии сервера и подробным логированием

const mineflayer = require('mineflayer');

// Получаем параметры из командной строки (их передаёт main.py)
const serverIp = process.argv[2];
const serverPort = parseInt(process.argv[3]) || 25565;
const botName = process.argv[4] || 'MineBot';

if (!serverIp) {
    console.log('❌ Ошибка: Не указан IP сервера!');
    process.exit(1);
}

console.log(`🤖 Запускаю бота ${botName} для подключения к ${serverIp}:${serverPort}...`);

// Создаём бота БЕЗ указания версии — она определится автоматически
const bot = mineflayer.createBot({
    host: serverIp,
    port: serverPort,
    username: botName,
    auth: 'offline' // для пиратских серверов. Если нужен лицензионный — замени на 'microsoft'
});

// Событие при успешном входе на сервер
bot.on('login', () => {
    console.log(`✅ Бот ${botName} успешно подключился к серверу!`);
    // Выводим версию, которую определил Mineflayer
    console.log(`🌐 Версия сервера (автоопределение): ${bot.version || 'неизвестно'}`);
});

// Событие, когда бот появляется в мире (загрузился)
bot.on('spawn', () => {
    console.log(`🌟 Бот ${botName} появился в мире!`);
});

// Событие при кике с сервера (самое важное для диагностики)
bot.on('kicked', (reason) => {
    console.log(`❌ Бот ${botName} был кикнут. Причина: ${reason}`);
    process.exit(1); // Завершаем процесс, чтобы Railway показал ошибку
});

// Событие при ошибке соединения или протокола
bot.on('error', (err) => {
    console.log(`⚠️ Ошибка у бота ${botName}:`, err.message);
    // Не завершаем процесс сразу, возможно, ошибка временная
});

// Событие при отключении от сервера (нормальное или из-за ошибки)
bot.on('end', (reason) => {
    console.log(`🔌 Бот ${botName} отключился от сервера. Причина: ${reason || 'неизвестна'}`);
    process.exit(0); // Завершаем процесс чисто
});

// Дополнительно: логируем всё, что бот говорит в чат (для отладки)
bot.on('message', (message) => {
    console.log(`[ЧАТ] ${message}`);
});

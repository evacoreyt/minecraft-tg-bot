// ===== minecraft_bot.js =====
// Эта программа создаёт одного Minecraft-бота.
// Она получает настройки (IP, порт, ник) из специальных переменных.

// Подключаем библиотеку для создания бота
const mineflayer = require('mineflayer');

// --- Получаем настройки ---
// Эти переменные мы будем передавать из главного Telegram-бота
const serverIp = process.argv[2];       // IP адрес сервера
const serverPort = parseInt(process.argv[3]) || 25565; // Порт (если не указан, ставим 25565)
const botName = process.argv[4] || 'MineBot';      // Имя бота (если не указано, ставим "MineBot")

// Проверяем, передали ли нам IP
if (!serverIp) {
    console.log('❌ Ошибка: Не указан IP сервера!');
    process.exit(1); // Завершаем программу с ошибкой
}

console.log(`🤖 Запускаю бота ${botName} для подключения к ${serverIp}:${serverPort}...`);

// --- Создаём бота ---
// Здесь мы используем настройки, которые получили [citation:10]
const bot = mineflayer.createBot({
    host: serverIp,
    port: serverPort,
    username: botName,
    // auth: 'offline' - означает, что сервер пиратский (не требует лицензии). Если сервер платный, нужно менять.
    auth: 'offline' 
});

// --- События бота (что он делает в разных ситуациях) ---

// Когда бот успешно зашёл на сервер
bot.on('login', () => {
    console.log(`✅ Бот ${botName} успешно подключился к серверу!`);
});

// Когда бота выкинуло с сервера (kicked)
bot.on('kicked', (reason) => {
    console.log(`❌ Бот ${botName} был кикнут. Причина: ${reason}`);
    process.exit(0); // Завершаем программу
});

// Когда произошла ошибка
bot.on('error', (err) => {
    console.log(`⚠️ Ошибка у бота ${botName}:`, err.message);
    // process.exit(1); // Можно завершить, а можно и оставить, чтобы бот пытался пережить ошибку
});

// Когда бот отключился от сервера
bot.on('end', (reason) => {
    console.log(`🔌 Бот ${botName} отключился от сервера.`);
    process.exit(0);
});

// Просто чтобы бот не молчал в консоли, когда подключится
bot.on('spawn', () => {
    console.log(`🌟 Бот ${botName} появился в мире!`);
});


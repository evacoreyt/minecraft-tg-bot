// minecraft_bot.js – обычный бот + режим ИИ (Gemini)
const mineflayer = require('mineflayer');
const Vec3 = require('vec3');

// ---------- Настройки ----------
const RECONNECT_DELAY = 10000;      // 10 секунд между попытками
const MAX_RECONNECT_ATTEMPTS = 20;  // максимальное число попыток
const CONNECTION_TIMEOUT = 30000;   // 30 секунд таймаут подключения

let shouldReconnect = true;
let reconnectAttempts = 0;
let loginSuccess = false;
let currentBot = null;
let loginTimeout = null;

// Режим ИИ
const AI_MODE = process.argv.includes('--ai');
const GEMINI_API_KEY = process.env.GEMINI_API_KEY;

if (AI_MODE && !GEMINI_API_KEY) {
    console.log('⚠️ Режим ИИ включён, но не задан GEMINI_API_KEY!');
    process.exit(1);
}

// Функция вызова Gemini API (асинхронная)
async function callGemini(prompt) {
    const url = `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=${GEMINI_API_KEY}`;
    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                contents: [{ parts: [{ text: prompt }] }]
            })
        });
        const data = await response.json();
        if (data.candidates && data.candidates[0].content) {
            return data.candidates[0].content.parts[0].text;
        }
        console.error('Ошибка Gemini:', data);
        return "Извините, я не могу ответить сейчас.";
    } catch (err) {
        console.error('Ошибка вызова Gemini:', err);
        return "Произошла ошибка при обращении к ИИ.";
    }
}

// Выполнение действий, описанных в ответе ИИ (упрощённый парсинг)
function executeAction(bot, actionText) {
    const lower = actionText.toLowerCase();
    // Пример: "пойти на 100 64 200"
    const moveMatch = lower.match(/(?:пойти|иди|move)\s+на\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)/);
    if (moveMatch) {
        const x = parseInt(moveMatch[1]);
        const y = parseInt(moveMatch[2]);
        const z = parseInt(moveMatch[3]);
        bot.chat(`Иду к ${x} ${y} ${z}`);
        bot.navigate.to(new Vec3(x, y, z));
        return;
    }
    // Копать впереди (если есть блок)
    const digMatch = lower.match(/(?:копать|dig)/);
    if (digMatch) {
        const block = bot.blockAt(bot.entity.position.offset(0, 0, 1));
        if (block && bot.canDigBlock(block)) {
            bot.chat('Начинаю копать...');
            bot.dig(block);
        } else {
            bot.chat('Не могу копать – нет блока впереди или он недоступен.');
        }
        return;
    }
    // Поставить блок (простейший пример – ставим камень под ноги)
    const placeMatch = lower.match(/(?:поставить|place)/);
    if (placeMatch) {
        const block = bot.blockAt(bot.entity.position.offset(0, -1, 0));
        if (block && bot.canDigBlock(block)) {
            bot.chat('Пытаюсь поставить камень под ноги...');
            const stone = bot.inventory.findInventoryItem(minecraftItem => minecraftItem.name === 'stone');
            if (stone) {
                bot.equip(stone, 'hand');
                bot.placeBlock(block, new Vec3(0, 1, 0));
            } else {
                bot.chat('У меня нет камня!');
            }
        }
        return;
    }
}

// Создание бота
function createBot() {
    const serverIp = process.argv[2];
    const serverPort = parseInt(process.argv[3]) || 25565;
    const botName = process.argv[4] || 'MineBot';

    console.log(`🤖 Попытка подключения бота ${botName} к ${serverIp}:${serverPort}...`);

    const options = {
        host: serverIp,
        port: serverPort,
        username: botName,
        auth: 'offline'
    };

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

    const bot = createBot();

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
        if (AI_MODE) {
            bot.chat('Привет! Я бот с искусственным интеллектом. Можешь написать мне в чат.');
        }
    });

    // Обработка сообщений (только если ИИ включён)
    if (AI_MODE) {
        bot.on('chat', async (username, message) => {
            if (username === bot.username) return;
            // Игнорируем слишком частые запросы (можно добавить throttle)
            console.log(`[CHAT] ${username}: ${message}`);
            const prompt = `Ты бот в Minecraft. Игрок ${username} сказал: "${message}". 
Ты должен ответить игроку в чате, а также можешь выполнить одно из действий: 
- пойти на координаты X Y Z (если указаны)
- копать впереди
- поставить блок (камень) под ноги
Если нужно выполнить действие, опиши его в ответе, например: "Иду на 100 64 200". 
Твой ответ (только текст, без лишних символов):`;
            const reply = await callGemini(prompt);
            console.log(`[AI] Ответ: ${reply}`);
            bot.chat(reply);
            executeAction(bot, reply);
        });

        bot.on('whisper', async (username, message) => {
            console.log(`[WHISPER] ${username}: ${message}`);
            const prompt = `Тебе пишет игрок ${username} в личку: "${message}". Ответь ему лично (whisper) и, если нужно, выполни действие.`;
            const reply = await callGemini(prompt);
            bot.whisper(username, reply);
            executeAction(bot, reply);
        });
    }

    // Стандартные обработчики для всех ботов
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
        console.log(`🔌 Бот ${bot.username} отключился. Причина: ${reason || 'неизвестна'}`);
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

// Запуск
attemptConnect();

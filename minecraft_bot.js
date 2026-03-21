// minecraft_bot.js – обычный бот + режим ИИ с поддержкой Ollama / OpenRouter / Gemini
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

// Выбор LLM по переменным окружения
const OLLAMA_URL = process.env.OLLAMA_URL;
const OPENROUTER_API_KEY = process.env.OPENROUTER_API_KEY;
const GEMINI_API_KEY = process.env.GEMINI_API_KEY;

// Модель по умолчанию для Ollama (можно переопределить переменной OLLAMA_MODEL)
const OLLAMA_MODEL = process.env.OLLAMA_MODEL || 'sweaterdog/andy-4:micro-q8_0';
// Модель для OpenRouter (бесплатная)
const OPENROUTER_MODEL = process.env.OPENROUTER_MODEL || 'mistralai/mistral-7b-instruct:free';

if (AI_MODE && !OLLAMA_URL && !OPENROUTER_API_KEY && !GEMINI_API_KEY) {
    console.log('⚠️ Режим ИИ включён, но не задан ни один источник (OLLAMA_URL, OPENROUTER_API_KEY, GEMINI_API_KEY)');
    process.exit(1);
}

// ---------- Фильтрация сообщений ----------
// Бот будет реагировать, если:
// - его упомянули по имени (например, "Kaine, привет" или "@Kaine")
// - сообщение начинается с его имени с двоеточием ("Kaine: ...")
// - это личное сообщение (whisper)
function shouldRespond(bot, username, message) {
    if (username === bot.username) return false;
    const lowerMsg = message.toLowerCase();
    const lowerName = bot.username.toLowerCase();
    return lowerMsg.includes(`@${lowerName}`) ||
           lowerMsg.startsWith(`${lowerName}:`) ||
           lowerMsg.startsWith(`${lowerName},`) ||
           message.startsWith('@');
}

// ---------- Троттлинг ----------
let lastRequestTime = 0;
const REQUEST_COOLDOWN_MS = 5000; // 5 секунд между запросами

function canMakeRequest() {
    const now = Date.now();
    if (now - lastRequestTime >= REQUEST_COOLDOWN_MS) {
        lastRequestTime = now;
        return true;
    }
    return false;
}

// ---------- Кэш ответов ----------
const responseCache = new Map();
const CACHE_TTL_MS = 10 * 60 * 1000; // 10 минут

function getCachedResponse(prompt) {
    const cached = responseCache.get(prompt);
    if (cached && Date.now() - cached.timestamp < CACHE_TTL_MS) {
        return cached.answer;
    }
    return null;
}

function setCachedResponse(prompt, answer) {
    responseCache.set(prompt, { answer, timestamp: Date.now() });
}

// ---------- Вызовы LLM ----------

// 1. Ollama (локальная)
async function callOllama(prompt) {
    const url = `${OLLAMA_URL}/api/generate`;
    const body = {
        model: OLLAMA_MODEL,
        prompt: prompt,
        stream: false,
        options: { temperature: 0.7, max_tokens: 150 }
    };
    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        const data = await response.json();
        if (data.response) {
            return data.response.trim();
        }
        console.error('Ошибка Ollama:', data);
        return "Извините, я не могу ответить сейчас.";
    } catch (err) {
        console.error('Ошибка вызова Ollama:', err);
        return "Произошла ошибка при обращении к ИИ.";
    }
}

// 2. OpenRouter (бесплатные модели)
async function callOpenRouter(prompt) {
    const url = 'https://openrouter.ai/api/v1/chat/completions';
    const body = {
        model: OPENROUTER_MODEL,
        messages: [
            { role: 'system', content: 'Ты бот в Minecraft. Отвечай кратко и по делу. Можешь выполнять действия: иди на координаты, копай, поставь блок.' },
            { role: 'user', content: prompt }
        ],
        max_tokens: 150,
        temperature: 0.7
    };
    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${OPENROUTER_API_KEY}`
            },
            body: JSON.stringify(body)
        });
        const data = await response.json();
        if (data.choices && data.choices[0].message) {
            return data.choices[0].message.content.trim();
        }
        console.error('Ошибка OpenRouter:', data);
        return "Извините, я не могу ответить сейчас.";
    } catch (err) {
        console.error('Ошибка вызова OpenRouter:', err);
        return "Произошла ошибка при обращении к ИИ.";
    }
}

// 3. Gemini (резервный)
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

// Основная функция вызова LLM (выбирает доступный)
async function callLLM(prompt) {
    if (OLLAMA_URL) {
        return await callOllama(prompt);
    } else if (OPENROUTER_API_KEY) {
        return await callOpenRouter(prompt);
    } else if (GEMINI_API_KEY) {
        return await callGemini(prompt);
    } else {
        return "Нет доступного API для ИИ.";
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
        // Требуется установка mineflayer-navigate или использование bot.pathfinder
        // Здесь упрощённо – просто сообщаем о намерении
        // Для реального движения нужен плагин pathfinder
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
            const stone = bot.inventory.findInventoryItem(item => item.name === 'stone');
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
            bot.chat('Привет! Я бот с искусственным интеллектом. Можешь написать мне в чат, упомянув моё имя.');
        }
    });

    // Обработка сообщений (только если ИИ включён)
    if (AI_MODE) {
        bot.on('chat', async (username, message) => {
            if (!shouldRespond(bot, username, message)) return;
            if (!canMakeRequest()) {
                bot.chat(`Извини, ${username}, я обрабатываю предыдущий запрос. Подожди немного.`);
                return;
            }

            console.log(`[CHAT] ${username}: ${message}`);

            // Проверка кэша
            const cacheKey = `${username}:${message}`;
            const cached = getCachedResponse(cacheKey);
            if (cached) {
                console.log(`[AI] Использую кэш: ${cached}`);
                bot.chat(cached);
                executeAction(bot, cached);
                return;
            }

            const prompt = `Ты бот в Minecraft по имени ${bot.username}. Игрок ${username} сказал: "${message}". 
Ты должен ответить игроку в чате, а также можешь выполнить одно из действий: 
- пойти на координаты X Y Z (если указаны)
- копать впереди
- поставить блок (камень) под ноги
Если нужно выполнить действие, опиши его в ответе, например: "Иду на 100 64 200". 
Твой ответ (только текст, без лишних символов):`;

            const reply = await callLLM(prompt);
            console.log(`[AI] Ответ: ${reply}`);
            setCachedResponse(cacheKey, reply);
            bot.chat(reply);
            executeAction(bot, reply);
        });

        bot.on('whisper', async (username, message) => {
            if (!canMakeRequest()) {
                bot.whisper(username, 'Подожди, я обрабатываю предыдущий запрос.');
                return;
            }
            console.log(`[WHISPER] ${username}: ${message}`);
            const prompt = `Тебе пишет игрок ${username} в личку: "${message}". Ответь ему лично (whisper) и, если нужно, выполни действие.`;
            const reply = await callLLM(prompt);
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

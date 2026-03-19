# Используем официальный образ Python
FROM python:3.11-slim

# Устанавливаем Node.js 18
RUN apt-get update && apt-get install -y curl && \
    curl -fsSL https://deb.nodesource.com/setup_18.x | bash - && \
    apt-get install -y nodejs && \
    apt-get clean

# Устанавливаем рабочую папку
WORKDIR /app

# Копируем файлы Python и устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем файлы Node.js и устанавливаем зависимости
COPY package.json package-lock.json ./
RUN npm install

# Копируем весь остальной проект
COPY . .

# Команда для запуска бота
CMD ["python", "main.py"]

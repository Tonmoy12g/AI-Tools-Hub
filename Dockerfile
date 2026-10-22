FROM python:3.10-slim

# ffmpeg ইনস্টল করা (ভয়েসের জন্য জরুরি)
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "bot.py"]

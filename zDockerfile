FROM python:3.10-slim

# ffmpeg এবং অন্যান্য সিস্টেম প্যাকেজ ইনস্টল
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "bot.py"]

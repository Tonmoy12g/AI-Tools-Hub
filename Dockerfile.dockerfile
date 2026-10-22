FROM python:3.10-slim

# সিস্টেম সফটওয়্যার ইনস্টল (ভয়েস, ভিডিও, ছবির জন্য)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "bot.py"]
# Gunakan base image Python 3.10 yang ringan
FROM python:3.10-slim

# Tetapkan direktori kerja
WORKDIR /app

# Salin dan install dependencies
COPY requirements.txt .
RUN apt-get update && apt-get install -y ffmpeg \
    && pip install --no-cache-dir -r requirements.txt

# Salin seluruh isi proyek ke container
COPY . .

# Buat folder untuk download media (kalau dibutuhkan)
RUN mkdir -p downloads

# Jalankan bot
CMD ["python3", "main.py"]

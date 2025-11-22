FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN apt-get update && apt-get install -y ffmpeg \
    && pip install --no-cache-dir -r requirements.txt

# Copy seluruh project
COPY . /app

# Override media agar tidak hilang
COPY media/ /app/media/

# Pastikan folder temp selalu ada (dan tidak terganggu)
RUN mkdir -p /app/temp_files /app/downloads

CMD ["python3", "main.py"]

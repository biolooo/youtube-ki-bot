FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY youtube_ki_bot /app/youtube_ki_bot
COPY docs /app/docs
COPY main.py /app/main.py
COPY reference_library.json /app/reference_library.json
COPY embedding_index.json /app/embedding_index.json
COPY video_taxonomy.json /app/video_taxonomy.json
COPY shorts_analysis.csv /app/shorts_analysis.csv
COPY top_video_references.csv /app/top_video_references.csv

EXPOSE 8000

CMD ["sh", "-c", "uvicorn youtube_ki_bot.api_app:app --host 0.0.0.0 --port ${PORT}"]

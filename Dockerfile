FROM mcr.microsoft.com/playwright/python:v1.48.0-jammy

WORKDIR /app
COPY requirements.txt .
RUN python3 -m pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE $PORT
CMD ["sh", "-c", "python3 -m uvicorn main:app --host 0.0.0.0 --port $PORT"]

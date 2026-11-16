FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY simsup_core.py service.py scenarios.json ./
CMD ["python", "-u", "service.py"]

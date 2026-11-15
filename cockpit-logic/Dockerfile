FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY logic.py dsky.py computer.py fmt.py service.py ./
CMD ["python", "-u", "service.py"]

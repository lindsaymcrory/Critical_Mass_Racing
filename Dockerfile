FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 0.0.0.0 is required inside a container -- 127.0.0.1 would be unreachable
# through the port mapping. debug/reload stay on; this is a personal local
# tool, not an internet-facing deployment.
ENV HOST=0.0.0.0
ENV PORT=8000

EXPOSE 8000

CMD ["python", "app.py"]

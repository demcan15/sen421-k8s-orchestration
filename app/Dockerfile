FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py .
ARG APP_VERSION=v1
ENV APP_VERSION=${APP_VERSION}
EXPOSE 8080
# One worker per pod so CPU usage maps cleanly to the HPA target.
CMD ["gunicorn", "-w", "1", "--threads", "4", "-b", "0.0.0.0:8080", "--graceful-timeout", "5", "main:app"]

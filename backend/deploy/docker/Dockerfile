FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml gunicorn.conf.py ./
RUN pip install --no-cache-dir ".[all]"

COPY . .

# Run with Gunicorn + UvicornWorker (see gunicorn.conf.py for config)
# Nginx is expected to proxy requests to Gunicorn on 127.0.0.1:8002
CMD ["gunicorn", "app.main:app", "--config", "gunicorn.conf.py"]

EXPOSE 8002

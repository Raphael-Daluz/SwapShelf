FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p /app/data && chmod 777 /app/data
RUN python manage.py collectstatic --noinput
ENV DATABASE_PATH=/app/data/swapshelf.db
ENV PORT=3000
EXPOSE 3000
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py seed && exec gunicorn --bind 0.0.0.0:${PORT:-3000} swapshelf.wsgi"]

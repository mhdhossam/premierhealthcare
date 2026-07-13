FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /premierhealthcare

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

RUN python manage.py makemigrations && python manage.py migrate

RUN python manage.py collectstatic --noinput

COPY . .

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh


EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
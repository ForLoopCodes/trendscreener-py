FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
COPY insta_likes_api.py .

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8000

# Use environment variables for credentials
ENV INSTAGRAM_USERNAME=""
ENV INSTAGRAM_PASSWORD=""

CMD ["uvicorn", "insta_likes_api:app", "--host", "0.0.0.0", "--port", "8000"]
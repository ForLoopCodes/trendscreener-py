FROM python:3.12-slim

WORKDIR /app

COPY insta_likes_api.py .

RUN pip install --no-cache-dir fastapi uvicorn instaloader pydantic

EXPOSE 8000

CMD ["uvicorn", "insta_likes_api:app", "--host", "0.0.0.0", "--port", "8000"]
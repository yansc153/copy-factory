FROM python:3.12-slim

WORKDIR /app
COPY app ./app
COPY scripts ./scripts
COPY README.md env.example Makefile ./
RUN mkdir -p data

ENV COPY_FACTORY_ENV=production
EXPOSE 8000
CMD ["python3", "-m", "app.web", "--host", "0.0.0.0", "--port", "8000"]

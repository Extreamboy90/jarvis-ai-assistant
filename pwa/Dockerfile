FROM python:3.11-slim

WORKDIR /app

# Copy PWA files
COPY . /app

# Expose port
EXPOSE 3001

# Run server
CMD ["python3", "serve.py"]

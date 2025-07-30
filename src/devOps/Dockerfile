# Dockerfile
FROM python:3.12-slim

# Install dependencies
RUN apt-get update && apt-get install -y \
	git \
    curl \
    docker.io \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*
    
# # Install curl and git, nadv change for slack work
# RUN apt-get update && \
#     apt-get install -y curl git && \
#     apt-get clean && \
#     rm -rf /var/lib/apt/lists/*

# Install Docker Compose plugin manually (v2.x)
RUN mkdir -p ~/.docker/cli-plugins && \
    curl -SL https://github.com/docker/compose/releases/download/v2.24.4/docker-compose-linux-x86_64 \
    -o ~/.docker/cli-plugins/docker-compose && \
    chmod +x ~/.docker/cli-plugins/docker-compose
    
WORKDIR /app
    
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY entrypoint.sh .
RUN chmod +x entrypoint.sh
COPY . .

EXPOSE 8080

ENTRYPOINT ["./entrypoint.sh"]

#CMD ["python", "webhook_server.py"]

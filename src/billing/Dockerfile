# Stage 1: Install dependencies
FROM python:3.11-slim AS builder
WORKDIR /app
COPY app/requirements.txt .
RUN pip install --user -r requirements.txt

# Stage 2: Runtime
FROM python:3.11-slim
WORKDIR /app
ENV PATH=/root/.local/bin:$PATH

COPY --from=builder /root/.local /root/.local

# Copy app code
COPY app/ ./app/

# Run the app
CMD ["python", "app/billing.py"]

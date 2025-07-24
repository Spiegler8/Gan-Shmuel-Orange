# Stage 1: Install dependencies
FROM python:3.11-slim AS builder
WORKDIR /ap
# Copy only requirements first for caching
COPY app/requirements.txt .
RUN pip install --user -r requirements.txt

# Stage 2: Runtime
FROM python:3.11-slim
WORKDIR /app
ENV PATH=/root/.local/bin:$PATH
COPY --from=builder /root/.local /root/.local
COPY app/ .
CMD ["uvicorn", "billing:app", "--host", "0.0.0.0", "--port", "8000"]


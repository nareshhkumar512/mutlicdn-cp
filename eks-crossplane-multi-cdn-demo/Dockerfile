FROM python:3.11-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl unzip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY adapters/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY adapters/ /app/
COPY terraform/ /app/terraform/

# Ensure install_terraform.sh is executable after copying
RUN chmod +x /app/install_terraform.sh

ENTRYPOINT ["/app/install_terraform.sh"]
CMD ["python", "/app/main.py"]

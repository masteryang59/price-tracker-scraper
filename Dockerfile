FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

COPY requirements.txt .
# Install the Chromium build that matches the pinned playwright package, plus its system libraries.
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install --with-deps --only-shell chromium

COPY pricetracker ./pricetracker
COPY demo_shop ./demo_shop

RUN useradd --create-home tracker && mkdir data outbox && chown tracker data outbox
USER tracker

ENTRYPOINT ["python", "-m", "pricetracker"]
CMD ["watch", "--every", "6h"]
ENV DECODE_PAYLOAD=true
ENV RESIZE_IMAGE=true
ENV VERIFY_TOKEN=true
ENV DECODE_PAYLOAD=true
ENV RESIZE_IMAGE=true
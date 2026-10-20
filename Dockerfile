FROM python:3.13-slim
RUN useradd --create-home --uid 10001 universal
WORKDIR /app
COPY --chown=universal:universal server.py backup.py ./
COPY --chown=universal:universal public ./public
RUN mkdir /data && chown universal:universal /data
USER universal
ENV OS_DATA_DIR=/data PYTHONUNBUFFERED=1
EXPOSE 8765
CMD ["python", "server.py", "--host", "0.0.0.0", "--port", "8765"]

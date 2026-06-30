FROM python:3.12-alpine
RUN pip install --no-cache-dir requests prometheus-client
COPY exporter.py /exporter.py
CMD ["python", "/exporter.py"]

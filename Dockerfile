FROM apache/airflow:3.3.2-python3.12

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir "apache-airflow==3.3.2" -r /tmp/requirements.txt && pip check

WORKDIR /opt/warehouse
ENV PYTHONPATH=/opt/warehouse/src
COPY --chown=airflow:root . .

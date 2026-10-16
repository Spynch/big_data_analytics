FROM apache/airflow:3.3.2-python3.12
COPY requirements.txt /tmp/requirements.txt
COPY requirements.lock /tmp/requirements.lock
COPY docker/airflow/constraints-3.12.txt /tmp/constraints.txt
RUN pip install --no-cache-dir 'apache-airflow==3.3.2' -r /tmp/requirements.txt \
    --constraint /tmp/constraints.txt --constraint /tmp/requirements.lock \
    && pip check
ENV PYTHONPATH=/opt/warehouse/src
WORKDIR /opt/warehouse

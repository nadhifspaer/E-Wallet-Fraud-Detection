FROM apache/airflow:3.3.2-python3.11

# system library required by lightgbm
USER root
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# batch scoring dependencies pinned by the official constraints
USER airflow
COPY airflow/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    --constraint https://raw.githubusercontent.com/apache/airflow/constraints-3.3.2/constraints-3.11.txt
ENV PYTHONPATH=/opt/project
RUN mkdir -p /opt/airflow/auth && chmod g=u /opt/airflow/auth

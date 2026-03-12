FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /workspace

COPY internal/aasrepository/benchmark_results/requirements.txt /workspace/internal/aasrepository/benchmark_results/requirements.txt
RUN pip install --no-cache-dir -r /workspace/internal/aasrepository/benchmark_results/requirements.txt

COPY internal/aasrepository/benchmark_results /workspace/internal/aasrepository/benchmark_results
COPY internal/aasrepository/integration_tests/bodies/post /workspace/internal/aasrepository/integration_tests/bodies/post

WORKDIR /workspace/internal/aasrepository/benchmark_results

ENTRYPOINT ["python", "benchmark.py"]

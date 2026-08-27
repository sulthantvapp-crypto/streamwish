FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=5000
ENV PROXY=http://zmglmvwl:puz74ldkgj3f@31.59.20.176:6754
ENV DB_URL=https://raw.githubusercontent.com/ytbro8326-sudo/primesrc_single_flaresolver/refs/heads/main/custom_merged_data.json?token=GHSAT0AAAAAAEC6VY7K65RBF6X7GCMHKWBY2UQAW3A
ENV DB_REFRESH_SECS=3600

EXPOSE 5000

CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:5000", "--workers", "2", "--threads", "4", "--timeout", "120"]

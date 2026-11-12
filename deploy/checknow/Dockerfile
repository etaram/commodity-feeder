# The check-now worker (leads/check_now.py): only the Python packages the company check needs (the same list as
# .github/workflows/company-check.yml). The code is not baked in: docker-compose.server.prod.yml mounts the
# server-instance checkout read-only at /app, so a server-up with new code and a restart is enough.
FROM python:3.12-slim
RUN pip install --no-cache-dir requests google-auth pycountry phonenumbers pypinyin certifi \
 && useradd -r -u 10001 -m worker
USER worker
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
CMD ["python", "-m", "leads.check_now"]

FROM python:3.11-buster

RUN pip install poetry==1.5.1

RUN poetry config virtualenvs.create false

COPY ./pyproject.toml ./poetry.lock* ./

RUN poetry install --no-interaction --no-ansi --no-root --no-directory
ENV DEBUG="${DEBUG}" \
    PYTHONUNBUFFERED="true" \
    PYTHONPATH="/"

COPY ./chatbot_api/*.py ./
COPY ./chatbot_api/csv ./csv
WORKDIR ./
RUN poetry install  --no-interaction --no-ansi

# Copy the .env file
COPY ./.env ./
CMD exec uvicorn chatbot_api.main:app --host 0.0.0.0 --port 8000
#CMD ["sh", "entrypoint.sh"]

# Use Python 3.11 image from Docker Hub as the base image
FROM python:3.11-buster

# Install poetry, a dependency management tool, at a specific version
RUN pip install poetry==1.5.1

# Configure poetry to not create a virtual environment inside the Docker container
RUN poetry config virtualenvs.create false

# Copy the project's dependency files to the container
COPY ./pyproject.toml ./poetry.lock* ./

# Install the project dependencies without installing the project itself
# This is done to ensure that dependencies are cached and only re-installed if they change
RUN poetry install --no-interaction --no-ansi --no-root --no-directory

# Set environment variables:
# - DEBUG: to control debug mode
# - PYTHONUNBUFFERED: to ensure logs are outputted immediately
# - PYTHONPATH: to ensure Python modules are correctly imported from the current directory
ENV DEBUG="${DEBUG}" \
    PYTHONUNBUFFERED="true" \
    PYTHONPATH="/"

# Copy the Python source code into the container
COPY ./chatbot_api/*.py ./

# Set the working directory to the current directory (where the source code is located)
WORKDIR ./

# Install the project itself using poetry
RUN poetry install  --no-interaction --no-ansi

# Copy the environment variables file into the container
COPY ./.env ./

# Define the command to run the application using uvicorn
# This command starts the FastAPI application on host 0.0.0.0 and port 8000
CMD exec uvicorn chatbot_api.main:app --host 0.0.0.0 --port 8000

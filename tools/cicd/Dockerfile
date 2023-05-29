FROM accelbyte/codegen:latest AS codegen

# Keeps Python from generating .pyc files in the container
ENV PYTHONDONTWRITEBYTECODE=1

# Turns off buffering for easier container logging
ENV PYTHONUNBUFFERED=1

WORKDIR /app
COPY . .

RUN python -m pip install --requirement requirements.txt

ENTRYPOINT [ "python", "cicd.py" ]

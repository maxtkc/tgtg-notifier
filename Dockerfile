FROM python:3.9-slim

RUN apt update && apt install -y curl build-essential
RUN curl -sSL https://raw.githubusercontent.com/python-poetry/poetry/master/install-poetry.py | python -

COPY ./pyproject.toml ./poetry.lock /

WORKDIR /tgtg-notifier

RUN /root/.local/bin/poetry install

COPY ./tgtg_notifier /tgtg-notifier/tgtg_notifier

# CMD ls -R /tgtg-notifier
CMD ["/root/.local/bin/poetry", "run", "python", "/tgtg-notifier/tgtg_notifier/main.py"]

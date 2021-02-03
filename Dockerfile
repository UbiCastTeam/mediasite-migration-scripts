FROM debian:10

RUN apt update && apt install -y \
        python3-coverage \
        python3-requests \
        make \
        flake8 \
        python3-pip \
    && apt clean && rm -rf /var/lib/apt/lists/*

WORKDIR /src

COPY requirements-pip.txt /src

RUN pip3 install -r requirements-pip.txt

ENV PYTHONPATH "/src/mediasite_migration_scripts:${PYTHONPATH}"
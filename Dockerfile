FROM debian:bullseye

RUN apt update && apt install -y \
        python3-coverage \
        python3-requests \
        make \
        flake8 \
        python3-pip \
        libmediainfo-dev \
    && apt clean && rm -rf /var/lib/apt/lists/*

WORKDIR /src

COPY requirements-pip.txt /src

RUN pip3 install -r requirements-pip.txt

ENV PYTHONPATH "/src/mediasite_migration_scripts:${PYTHONPATH}"

RUN ln -sfn "/src/mediasite_migration_scripts" "/usr/lib/python3/dist-packages/"
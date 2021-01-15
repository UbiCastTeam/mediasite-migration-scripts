build:
	docker build -t mediasite -f Dockerfile .

script: build
	docker run -it \
		-v ${CURDIR}:/src \
		--rm mediasite \
		python3 mediasite_script.py

script_dev: build
ifeq ($(is_build),)
	make build
endif
	docker run -it \
		-v ${CURDIR}:/src \
		-w /src \
		--rm mediasite \
		python3 mediasite_script.py --info

script_verbose: build
	docker run -it \
		-v ${CURDIR}:/src \
		--rm mediasite \
		python3 mediasite_script.py --verbose

stats: build
	docker run -it \
		-v ${CURDIR}:/src \
		--rm mediasite \
		python3 mediasite_script.py --stats

shell: build
	docker run -it \
		-v ${CURDIR}:/src \
		--rm mediasite \
		/bin/bash

local_script:
	python3 mediasite_script.py --info

local_script_verbose:
	python3 mediasite_script.py --verbose

local_stats:
	python3 mediasite_script.py --stats

build:
	docker build -t mediasite -f Dockerfile .

shell: build
	docker run -it \
		-v ${CURDIR}:/src \
		--rm mediasite \
		/bin/bash

import_data: build
	docker run -it \
		-v ${CURDIR}:/src \
		--rm mediasite \
		python3 bin/import_data.py $(ARGS)

analyze_data: build
	docker run -it \
		-v ${CURDIR}:/src \
		--rm mediasite \
		python3 bin/analyze_data.py $(ARGS)

import_media: build
	docker run -it \
		-v ${CURDIR}:/src \
		--rm mediasite \
		python3 bin/import_media.py $(ARGS)

tests: build
	docker run -it \
		-v ${CURDIR}:/src \
		--rm mediasite \
		python3 -m unittest tests/*.py $(ARGS)

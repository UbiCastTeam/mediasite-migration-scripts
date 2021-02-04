build:
	docker build -t mediasite -f Dockerfile .

bash: build
	docker run -it \
		-v ${CURDIR}:/src \
		--rm mediasite \
		/bin/bash

import_data: build
	docker run -it \
		-v ${CURDIR}:/src \
		--rm mediasite \
		python3 bin/import_data.py

import_data_dev: build
	docker run -it \
		-v ${CURDIR}:/src \
		--rm mediasite \
		python3 bin/import_data.py --info

import_data_verbose: build
	docker run -it \
		-v ${CURDIR}:/src \
		--rm mediasite \
		python3 bin/import_data.py --verbose

analyze_data: build import_data
	docker run -it \
		-v ${CURDIR}:/src \
		--rm mediasite \
		python3 bin/analyze_data.py


analyze_data_dev: build import_data_dev
	docker run -it \
		-v ${CURDIR}:/src \
		--rm mediasite \
		python3 bin/analyze_data.py --info


analyze_data_verbose: build import_data_verbose
	docker run -it \
		-v ${CURDIR}:/src \
		--rm mediasite \
		python3 bin/analyze_data.py --verbose


analyze_data_doctor: build import_data_dev
	docker run -it \
		-v ${CURDIR}:/src \
		--rm mediasite \
		python3 bin/analyze_data.py --doctor

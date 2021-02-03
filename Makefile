build:
	docker build -t mediasite -f Dockerfile .
	# export PYTHONPATH=${shell echo $PYTHONPATH}:/src/

script: build
	docker run -it \
		-v ${CURDIR}:/src \
		--rm mediasite \
		python3 mediasite_script.py

script_dev: build
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

script_doctor: build
	docker run -it \
			-v ${CURDIR}:/src \
			-w /src \
			--rm mediasite \
			python3 mediasite_script.py --doctor

stats: build
	docker run -it \
		-v ${CURDIR}:/src \
		--rm mediasite \
		python3 mediasite_script.py --stats

bash: build
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

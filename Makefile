build:
	docker build -t mediasite -f Dockerfile .

lint: build
	docker run -it \
		-v ${CURDIR}:/src \
		--rm mediasite \
		flake8 --ignore=E501,E265,W503,W505 --exclude=.git/,.virtualenv/,__pycache__/,build/,submodules/,env/

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

migrate: build
	docker run -it \
		-v ${CURDIR}:/src \
		--rm mediasite \
		python3 bin/migrate.py $(ARGS)

tests: build
	docker run -it \
		-v ${CURDIR}:/src \
		--rm mediasite \
		python3 -m unittest tests/*.py $(ARGS)

e2e_tests: build
	docker run -it \
		-v ${CURDIR}:/src \
		--rm mediasite \
		python3 -m unittest tests/e2e/*.py $(ARGS)

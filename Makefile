build:
	docker build -t mediasite -f docker/Dockerfile .

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

tests_e2e: build
	docker run -it \
		-v ${CURDIR}:/src \
		--rm mediasite \
		python3 -m unittest tests/e2e/*.py $(ARGS)

tests_e2e_ext:
	docker run -it \
		-v ${CURDIR}:/src \
		--rm mediasite \
		python3 -m unittest tests/e2e/e2e_data_extractor.py $(ARGS)

tests_e2e_mdtr: build
	docker run -it \
		-v ${CURDIR}:/src \
		--rm mediasite \
		python3 -m unittest tests/e2e/e2e_mediatransfer.py $(ARGS)

merge_build:
	docker build -t mediasite-merge -f docker/Dockerfile.arch .

merge_shell:
	docker run --rm -w /src -v ${CURDIR}:/src -it mediasite-merge /bin/bash

merge_run:
	docker run --rm -w /src -v ${CURDIR}:/src -it mediasite-merge python3 bin/merge.py $(ARGS)

merge_all:
	docker run --rm -w /src -e PYTHONPATH=/src -v ${CURDIR}:/src -it mediasite-merge python3 bin/batch_merge.py /src/downloads/composite

clean_collect:
	sudo rm -rf *mediasite_*.json presentations_*.txt samples.json

clean_migrate:
	sudo rm -rf downloads/composite redirections.json *mediaserver_data.json

clean_merge:
	sudo rm -f downloads/composite/*/composite.mp4 downloads/composite/*/mediaserver_layout.json

clean:
	$(MAKE) clean_collect
	$(MAKE) clean_migrate
	$(MAKE) clean_merge

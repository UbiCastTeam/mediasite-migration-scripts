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
		python3 bin/import_data.py $(ARGS)

analyze_data: build
	docker run -it \
		-v ${CURDIR}:/src \
		--rm mediasite \
		python3 bin/analyze_data.py $(ARGS)

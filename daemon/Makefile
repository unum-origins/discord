ACCOUNT?=$(shell cat ../ACCOUNT)
IMAGE=unum-origins-discord-daemon
VERSION?=dev
DEBUG_PORT=24437
TTY=$(shell if tty -s; then echo "-it"; fi)
VOLUMES=-v ${PWD}/lib/:/opt/service/lib/ \
		-v ${PWD}/bin/:/opt/service/bin/ \
		-v ${PWD}/test/:/opt/service/test/ \
		-v ${PWD}/.pylintrc:/opt/service/.pylintrc
ENVIRONMENT=-e PYTHONDONTWRITEBYTECODE=1 \
			-e PYTHONUNBUFFERED=1 \
			-e test="python -m unittest -v" \
			-e debug="python -m ptvsd --host 0.0.0.0 --port 5678 --wait -m unittest -v"

.PHONY: build shell debug test lint image push

build:
	docker build . -t $(ACCOUNT)/$(IMAGE):$(VERSION)

shell:
	-docker run $(TTY) --rm $(VOLUMES) $(ENVIRONMENT) $(ACCOUNT)/$(IMAGE):$(VERSION) sh

debug:
	docker run $(TTY) $(VOLUMES) $(ENVIRONMENT) -p 127.0.0.1:$(DEBUG_PORT):5678 $(ACCOUNT)/$(IMAGE):$(VERSION) sh -c "python -m ptvsd --host 0.0.0.0 --port 5678 --wait -m unittest discover -v test"

test:
	docker run $(TTY) $(VOLUMES) $(ENVIRONMENT) $(ACCOUNT)/$(IMAGE):$(VERSION) sh -c "coverage run -m unittest discover -v test && coverage report -m --include 'lib/*.py'"

lint:
	docker run $(TTY) $(VOLUMES) $(ENVIRONMENT) $(ACCOUNT)/$(IMAGE):$(VERSION) sh -c "pylint --rcfile=.pylintrc lib/"

image: build

push:
	docker push $(ACCOUNT)/$(IMAGE):$(VERSION)

semver:
	docker pull $(ACCOUNT)/$(IMAGE):$(VERSION)
	docker tag $(ACCOUNT)/$(IMAGE):$(VERSION) $(ACCOUNT)/$(IMAGE):$(SEMVER)
	docker push $(ACCOUNT)/$(IMAGE):$(SEMVER)

VERSION?=$(shell cat VERSION)
TILT_PORT=7637
INSTALL=python:3.8.5-alpine3.12
VOLUMES=-v ${PWD}/VERSION:/opt/service/VERSION \
		-v ${PWD}/setup.py:/opt/service/setup.py
.PHONY: up down setup tag untag

up:
	kubectx docker-desktop
	mkdir -p secret
	mkdir -p config
	# cnc-forge: up
	tilt --port $(TILT_PORT) up

down:
	kubectx docker-desktop
	tilt down

setup:
	docker run $(TTY) $(VOLUMES) $(INSTALL) sh -c "cp -r /opt/service /opt/install && \
	cd /opt/install/ && python setup.py install && \
	python -m ledger"

tag:
	-git tag -a $(VERSION) -m "Version $(VERSION)"
	git push origin --tags

untag:
	-git tag -d $(VERSION)
	git push origin ":refs/tags/$(VERSION)"

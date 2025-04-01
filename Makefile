VERSION?=$(shell cat VERSION)
TILT_PORT=7637
INSTALL=python:3.10.8-alpine3.16
VOLUMES=-v ${PWD}/daemon/:/opt/service/daemon/ \
		-v ${PWD}/VERSION:/opt/service/VERSION \
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
	apk add git && \
	pip install git+https://github.com/unum-apps/ledger@0.1.3 && \
	cd /opt/install/ && python setup.py install && \
	python -m unum_discord"

tag:
	-git tag -a $(VERSION) -m "Version $(VERSION)"
	git push origin --tags

untag:
	-git tag -d $(VERSION)
	git push origin ":refs/tags/$(VERSION)"

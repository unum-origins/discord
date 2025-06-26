VERSION?=$(shell cat VERSION)
TILT_PORT=7637
SEMVER=$(shell cat VERSION)
INSTALL=python:3.10.8-alpine3.16
VOLUMES=-v ${PWD}/daemon/:/opt/service/daemon/ \
		-v ${PWD}/VERSION:/opt/service/VERSION \
		-v ${PWD}/setup.py:/opt/service/setup.py
.PHONY: secret up down setup tag semver untag

secret:
	mkdir -p secret
	test -f secret/discord.json || echo '{"token": ""}' > secret/discord.json

up:
	kubectx docker-desktop
	mkdir -p config
	# cnc-forge: up
	tilt --port $(TILT_PORT) up

down:
	kubectx docker-desktop
	tilt down

tag:
	-git tag -a $(VERSION) -m "Version $(VERSION)"
	git push origin --tags

semver:
	cd daemon; VERSION=$(VERSION) SEMVER=$(SEMVER) make semver;

untag:
	-git tag -d $(VERSION)
	git push origin ":refs/tags/$(VERSION)"

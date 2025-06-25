CLUSTER="do-{{ unum }}-unum"
NAMESPACE="discord"
SERVICE="gui"
LOCAL_PORT=7601
.PHONY: tfenv init remote install uninstall

tfenv:
	tfenv use 1.10.5

init: tfenv
	terraform init

install: init
	terraform apply

uninstall: init
	terraform destroy

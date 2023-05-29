# Copyright (c) 2023 AccelByte Inc. All Rights Reserved.
# This is licensed software from AccelByte Inc, for limitations
# and restrictions contact your company contract manager.

VENV_DIR := venv

ifeq ($(PYTHON),)
	ifeq ($(OS), Windows_NT)
		PYTHON := python
		PYTHOND := Scripts
		PYTHONX := python.exe
	else
		PYTHON := python3
		PYTHOND := bin
		PYTHONX := python
	endif
endif

PYTHONE := $(PYTHOND)/$(PYTHONX)
PYTHONV := $(VENV_DIR)/$(PYTHONE)

DOCKER_FILE := Dockerfile
DOCKER_MOUNT_DIR := $(PWD)
DOCKER_TAG_VERSION := latest
DOCKER_TAG := accelbyte/grpc-plugin-proto-cicd:$(DOCKER_TAG_VERSION)

setup:
	$(PYTHON) -m venv $(VENV_DIR)
	$(PYTHONV) -m pip install --upgrade pip

install_package:
	@test -n "$(PKG_PATH)" || (echo "PKG_PATH is not set" ; exit 1)
	$(PYTHONV) -m pip install $(PKG_PATH)

style:
	$(PYTHONV) -m black .

run:
	@test -n "$(SPEC_PATH)" || (echo "SPEC_PATH is not set" ; exit 1)
	$(PYTHONV) cicd.py \
		../../asyncapi/templates \
		$(SPEC_PATH) \
		../../asyncapi.new && \
		rm -rf ../../asyncapi && \
		mv "../../asyncapi.new" "../../asyncapi"

dbuild:
	@test -n "$(CODEGEN_SDK_PATH)" || (echo "CODEGEN_SDK_PATH is not set" ; exit 1)
	cd $(CODEGEN_SDK_PATH) && \
		docker build \
			--tag accelbyte/codegen:latest \
			--file Dockerfile.proto \
			.
	docker build \
		--tag $(DOCKER_TAG) \
		--file $(DOCKER_FILE) \
		.

drun:
	@test -n "$(SPEC_PATH)" || (echo "SPEC_PATH is not set" ; exit 1)
	rm -rf $$(readlink -f ../..)/asyncapi.new && mkdir $$(readlink -f ../..)/asyncapi.new && \
		docker run --rm --tty --user $$(id -u):$$(id -g) \
			--volume $(SPEC_PATH):/data/source \
			--volume $$(readlink -f ../..)/asyncapi/templates:/data/templates \
			--volume $$(readlink -f ../..)/asyncapi.new:/data/destination \
			$(DOCKER_TAG) \
			/data/templates \
			/data/source \
			/data/destination && \
		rm -rf $$(readlink -f ../..)/asyncapi && \
		mv $$(readlink -f ../..)/asyncapi.new $$(readlink -f ../..)/asyncapi

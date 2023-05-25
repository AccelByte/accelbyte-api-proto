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

style:
	$(PYTHONV) -m black .

run:
	@test -n "$(JUSTICE_API_SPECIFICATION_REPO_PATH)" || (echo "JUSTICE_API_SPECIFICATION_REPO_PATH is not set" ; exit 1)
	rm -f "$(PWD)/run.err"
	$(PYTHONV) cicd.py \
		../../asyncapi/templates \
		$(JUSTICE_API_SPECIFICATION_REPO_PATH) \
		../../asyncapi.new \
		|| touch "$(PWD)/run.err"
	[ ! -f "$(PWD)/run.err" ]
	rm -rf ../../asyncapi
	mv "../../asyncapi.new" "../../asyncapi"
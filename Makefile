# Copyright (c) 2022 AccelByte Inc. All Rights Reserved.
# This is licensed software from AccelByte Inc, for limitations
# and restrictions contact your company contract manager.

SHELL := /bin/bash

COMPARE_AGAINST_BRANCH=origin/master

lint:
	docker run -t --rm --volume $$(pwd):/workspace --workdir /workspace bufbuild/buf:1.31.0 lint

breaking:
	docker run -t --rm --volume $$(pwd):/workspace --workdir /workspace bufbuild/buf:1.31.0 breaking \
    	--against ".git#branch=$(COMPARE_AGAINST_BRANCH)"

governance: check_governance_package_name_all check_governance_version_comment_all

check_governance_package_name:
	@test -n "$(FILE_PATH)" || (echo "FILE_PATH is not set" ; exit 1)
	@grep -zoqP 'package accelbyte(\.[^.\n]+)(\.[^.\n]+)?(\.[^.\n]+)(\.v[0-9]+)?;' $(FILE_PATH); \
		if [ $$? -ne 0 ]; then \
		  echo "[FAIL] $(FILE_PATH)"; \
		  echo -e "\tthe proto file should have package with the following pattern:"; \
		  echo -e "\t..."; \
		  echo -e "\tpackage accelbyte.<service_name>[.subproject].<feature>[.version];"; \
		  echo -e "\t..."; \
		  exit 1; \
		else \
		  echo "[OK] $(FILE_PATH)"; \
		fi

check_governance_package_name_all:
	@echo "Checking package name on all .proto file"
	@find asyncapi -type f -iname '*.proto' | xargs -I '{}' make -s check_governance_package_name FILE_PATH='{}'
	@find proto -type f -iname '*.proto' | xargs -I '{}' make -s check_governance_package_name FILE_PATH='{}'

check_governance_version_comment:
	@test -n "$(FILE_PATH)" || (echo "FILE_PATH is not set" ; exit 1)
	@grep -zoqP 'package .*;(\r\n|\r|\n)// Version v\d+.\d+.\d+' $(FILE_PATH); \
		if [ $$? -ne 0 ]; then \
		  echo "[FAIL] $(FILE_PATH)"; \
		  echo -e "\tthe proto file should have version comment with the following pattern:"; \
		  echo -e "\t..."; \
		  echo -e "\tpackage accelbyte.service.feature;"; \
  		  echo -e "\t// Version v1.0.0"; \
		  echo -e "\t..."; \
		  exit 1; \
		else \
		  echo "[OK] $(FILE_PATH)"; \
		fi

check_governance_version_comment_all:
	@echo "Checking version comment on all .proto file"
	@find asyncapi -type f -iname '*.proto' | xargs -I '{}' make -s check_governance_version_comment FILE_PATH='{}'
	@find proto -type f -iname '*.proto' | xargs -I '{}' make -s check_governance_version_comment FILE_PATH='{}'

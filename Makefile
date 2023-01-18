# Copyright (c) 2022 AccelByte Inc. All Rights Reserved.
# This is licensed software from AccelByte Inc, for limitations
# and restrictions contact your company contract manager.

SHELL := /bin/bash

COMPARE_AGAINST_BRANCH=origin/master

breaking:
	-git ls-tree -r $(COMPARE_AGAINST_BRANCH) | grep ".*\.proto$$" > /dev/null; \
	if [ $$? -eq 0 ]; then \
	  echo "Comparing current branch proto files with $(COMPARE_AGAINST_BRANCH)"; \
	  docker run --rm --volume $$(pwd):/workspace --workdir /workspace bufbuild/buf breaking \
      	--against ".git#branch=$(COMPARE_AGAINST_BRANCH)" \
      	--config '{"version":"v1","breaking":{"use":["FILE"]}}'; \
    else \
   	  echo "No proto files to compare to in $(COMPARE_AGAINST_BRANCH), SKIP"; \
   	fi

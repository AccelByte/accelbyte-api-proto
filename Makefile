# Copyright (c) 2022 AccelByte Inc. All Rights Reserved.
# This is licensed software from AccelByte Inc, for limitations
# and restrictions contact your company contract manager.

SHELL := /bin/bash

breaking:
	docker run --rm --volume $$(pwd):/workspace --workdir /workspace bufbuild/buf breaking \
	--against ".git#branch=origin/master" \
	--config '{"version":"v1","breaking":{"use":["FILE"]}}'
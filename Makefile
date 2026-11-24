# One-command entry points. Run from the repo root.
#   make image       build the .deb stage and then the final image
#   make self-test   run the compat test with upstream as both sides (proves the harness works)
#   make test        run the compat test: upstream vs our image
ECHO_IMAGE     ?= echo-nginx:test
UPSTREAM_IMAGE ?= nginx:1.25-bookworm
PYTHON         ?= python3

.PHONY: deb image self-test test

deb:
	docker build -f build/Dockerfile -t echo-nginx-build build/

image: deb
	docker build -f Containerfile -t $(ECHO_IMAGE) .

self-test:
	ECHO_IMAGE=$(UPSTREAM_IMAGE) UPSTREAM_IMAGE=$(UPSTREAM_IMAGE) $(PYTHON) test/compat_test.py

test:
	ECHO_IMAGE=$(ECHO_IMAGE) UPSTREAM_IMAGE=$(UPSTREAM_IMAGE) $(PYTHON) test/compat_test.py

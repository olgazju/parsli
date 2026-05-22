# Refuse to install any package uploaded to PyPI in the last 7 days.
# Newly published releases are a common supply-chain attack vector;
# waiting 7 days lets the community catch malicious uploads before they land here.
PRIOR_TO := $(shell date -v-7d +%F)

.PHONY: install install-dev test

install:
	PIP_UPLOADED_PRIOR_TO=$(PRIOR_TO) pip install -e .

install-dev:
	PIP_UPLOADED_PRIOR_TO=$(PRIOR_TO) pip install -e ".[dev]"

test:
	python -m pytest tests/ -v

SHELL = /bin/bash
VIRTUALENV_DIR = ${HOME}/.virtualenv

.PHONY: dev
dev: ${VIRTUALENV_DIR}/bedwetter
	source ${VIRTUALENV_DIR}/bedwetter/bin/activate && \
		pip3 install -U bandit black pip && \
		pip3 install --editable .

.PHONY: install
install: ${VIRTUALENV_DIR}/bedwetter
	source ${VIRTUALENV_DIR}/bedwetter/bin/activate && \
		pip3 install -U pip && \
		pip3 install --upgrade .

${VIRTUALENV_DIR}/bedwetter:
	mkdir -p ${VIRTUALENV_DIR}
	cd ${VIRTUALENV_DIR} && python3 -m venv bedwetter

.PHONY: lint
lint:
	-bandit -r .
	-black bedwetter

.DEFAULT_GOAL := install

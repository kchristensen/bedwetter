SHELL = /bin/bash
VIRTUALENV_DIR = ${HOME}/.virtualenv

.PHONY: dev
dev: ${VIRTUALENV_DIR}/bedwetter
	source ${VIRTUALENV_DIR}/bedwetter/bin/activate && \
		pip3.7 install -U flake8 pip && \
		pip3.7 install --editable .

.PHONY: install
install: ${VIRTUALENV_DIR}/bedwetter
	source ${VIRTUALENV_DIR}/bedwetter/bin/activate && \
		pip3.7 install -U pip && \
		pip3.7 install --upgrade .

${VIRTUALENV_DIR}/bedwetter:
	mkdir -p ${VIRTUALENV_DIR}
	cd ${VIRTUALENV_DIR} && python3.7 -m venv bedwetter

.PHONY: lint
lint:
	-flake8

.DEFAULT_GOAL := install
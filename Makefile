### --------------------------------------------------------------------------------------------------------------------
### Variables
### (https://www.gnu.org/software/make/manual/html_node/Using-Variables.html#Using-Variables)
### --------------------------------------------------------------------------------------------------------------------

VENV ?= venv

# Other config
NO_COLOR=\033[0m
OK_COLOR=\033[32;01m
ERROR_COLOR=\033[31;01m
WARN_COLOR=\033[33;01m

### --------------------------------------------------------------------------------------------------------------------
### RULES
### (https://www.gnu.org/software/make/manual/html_node/Rule-Introduction.html#Rule-Introduction)
### --------------------------------------------------------------------------------------------------------------------
.PHONY: requirements dist

help:
	@echo "Please use \`make <target>' where <target> is one of"
	@echo "  run                        to run the service"
	@echo "  test                       to run unit tests"
	@echo "  setup                      to setup the working virtual environment, and to install requirements for development"
	@echo "  clean                      to remove the created virtualenv folder"
	@echo "  code-style                 to run pep8 on src"
	@echo "  dist        version=1.2.3  to build wheel distribution of version 1.2.3"
	@echo "  dist-upload version=1.2.3  to build + upload to PyPi wheel distributionof version 1.2.3"


setup: clean virtualenv requirements test-requirements

run:
	python3 $(CURDIR)/eks_rolling_update.py --help

test: code-style test-unit

test-unit:
	PYTHONPATH=$(CURDIR) nose2 --with-coverage

code-style:
	flake8 --ignore E501 eksrollup/

virtualenv:
	virtualenv -p python3 $(CURDIR)/$(VENV)

clean:
	rm -rf $(CURDIR)/$(VENV) $(CURDIR)/build $(CURDIR)/dist

requirements:
	$(CURDIR)/$(VENV)/bin/pip3 install -r requirements.txt

test-requirements:
	$(CURDIR)/$(VENV)/bin/pip3 install -r requirements-tests.txt

dist: check_version
	mkdir -p build && echo "VERSION = '$(version)'" > build/__version__.py
	python3 $(CURDIR)/setup.py sdist bdist_wheel

dist-upload: dist
	twine upload $(CURDIR)/dist/*

docker-dist:
	docker build . -t eks_rolling_update:latest

check_version:
ifndef version
	$(error Please specify release `version` argument.`)
endif
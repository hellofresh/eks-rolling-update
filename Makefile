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
.PHONY: requirements

help:
	@echo "Please use \`make <target>' where <target> is one of"
	@echo "  run         to run the service"
	@echo "  test        to run unit tests"
	@echo "  setup       to setup the working virtual environment, and to install requirements for development"
	@echo "  clean       to remove the created virtualenv folder"
	@echo "  code-style  to run pep8 on src"


setup: clean virtualenv requirements

run:
	python3 $(CURDIR)/eks_rolling_update.py --help

test: code-style test-unit

test-unit:
	PYTHONPATH=$(CURDIR) nose2 --with-coverage

code-style:
	flake8 --ignore E501 eks_rolling_update.py lib/

virtualenv:
	virtualenv -p python3 $(CURDIR)/$(VENV)

clean:
	rm -rf $(CURDIR)/$(VENV)

requirements:
	$(CURDIR)/$(VENV)/bin/pip3 install -r requirements.txt

test-requirements:
	$(CURDIR)/$(VENV)/bin/pip3 install -r requirements-tests.txt
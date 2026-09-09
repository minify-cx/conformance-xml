MINIFY_BIN ?= ../minify/minify
PYTHON ?= python3

.PHONY: all build-minify deps sync extract run smoke test dashboard clean

all: smoke

build-minify:
	$(MAKE) -C ../minify

deps:
	$(PYTHON) -m pip install -r requirements.txt

sync:
	$(PYTHON) tools/conformance.py sync

extract:
	$(PYTHON) tools/conformance.py extract

run: build-minify
	$(PYTHON) tools/conformance.py run --minify-bin $(MINIFY_BIN)

smoke: build-minify
	$(PYTHON) tools/conformance.py smoke --minify-bin $(MINIFY_BIN)

test:
	$(PYTHON) -m unittest discover -s tests -v

dashboard:
	$(PYTHON) tools/conformance.py dashboard

clean:
	rm -rf work generated results .state .nift/public .nift/.lock tests/__pycache__ tools/__pycache__

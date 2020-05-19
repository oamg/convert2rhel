IMAGE = convert2rhel

all: clean images tests lint

clean:
	@rm -rf build/ dist/ *.egg-info .pytest_cache/
	@find . -name '__pycache__' -exec rm -fr {} +
	@find . -name '*.pyc' -exec rm -f {} +
	@find . -name '*.pyo' -exec rm -f {} +

images:
	@docker build -f Dockerfiles/centos5 -t $(IMAGE)/centos5 .
	@docker build -f Dockerfiles/centos6 -t $(IMAGE)/centos6 .
	@docker build -f Dockerfiles/centos7 -t $(IMAGE)/centos7 .

tests:
	@docker run --rm -v $(shell pwd):/data:Z $(IMAGE)/centos5 ./run_unit_tests.sh
	@docker run --rm -v $(shell pwd):/data:Z $(IMAGE)/centos6 ./run_unit_tests.sh
	@docker run --rm -v $(shell pwd):/data:Z $(IMAGE)/centos7 ./run_unit_tests.sh

lint:
	pylint --rcfile=.pylintrc convert2rhel/

.PHONY: all clean images tests

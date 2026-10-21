.PHONY: install lint format typecheck test check train-synthetic train-real status rollback mlflow-ui serve export image

install:
	pip install -r requirements-dev.lock
	pip install --no-deps -e .

lint:
	ruff check src tests scripts

format:
	ruff format src tests scripts

typecheck:
	mypy src

test:
	pytest --cov=hotelml --cov-report=term-missing

check: lint typecheck test

train-synthetic:
	hotelml train --source synthetic --rows 20000

train-real:
	hotelml train --source hf

status:
	hotelml status

rollback:
	hotelml rollback

mlflow-ui:
	mlflow ui --backend-store-uri sqlite:///mlflow.db --port 5000

serve:
	uvicorn hotelml.api:app --host 127.0.0.1 --port 8000

export:
	hotelml export --output model-bundle

image:
	docker build -t hotelml:local .

run:
	uvicorn app.main:app --reload

test:
	pytest -q

docker-build:
	docker build -t cn-address-api .

docker-run:
	docker run -p 8000:8000 cn-address-api

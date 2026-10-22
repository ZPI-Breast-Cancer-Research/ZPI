from config.celery import app


@app.task(name="training.run")
def run(training_run_id: int) -> None:
    raise NotImplementedError

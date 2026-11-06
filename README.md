# warehouse-automation-qa

[![Tests](https://github.com/Younus98/warehouse-automation-qa/actions/workflows/tests.yml/badge.svg)](https://github.com/Younus98/warehouse-automation-qa/actions/workflows/tests.yml)

QA automation framework for a warehouse management system: API, UI, end-to-end flows and CI.

> Full documentation follows in a later step.

## Run the tests

```bash
pip install -r requirements.txt
python -m playwright install chromium
pytest                 # all tests
pytest -m smoke        # quick check
pytest tests/api       # API tests only
```

# InstaTrack Tests

This folder contains the automated tests for InstaTrack, ensuring that the backend logic, reporting, and services work correctly.

## How to Run Tests

### 1. Prerequisites
Ensure you have installed the development dependencies:
```bash
pip install -r requirements.txt
pip install pytest pytest-mock
```

### 2. Run All Tests
Execute the following command from the project root (`InstaTrack/`):
```bash
pytest
```

or specifically to force the mock database (recommended for unit tests):
```bash
USE_MOCK_DB=1 pytest
```

### 3. Understanding Output
- **Green points (.)**: Tests passed.
- **Red Fs (F)**: Tests failed. Check the error log printed below.

## Structure
- `conftest.py`: Configures the test environment (e.g., forces Mock DB).
- `test_*.py`: Individual test files for each service.

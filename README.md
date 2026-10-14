# H&M Recommendation Decision Lab

Local FastAPI application for analysing the supplied H&M Kaggle sample and demonstrating an AI-assisted weekly product-recommendation decision.

## Windows start

1. Keep the project folder intact.
2. Right-click `start.ps1` and choose **Run with PowerShell**, or open PowerShell in the folder and run:

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

3. Open <http://localhost:8000> if the browser does not open automatically.

The first run installs dependencies. Later starts are faster.

## Permanent public link with Render

1. Upload this project to a GitHub repository. Keep `data/processed/app_data.json.gz` in the repository.
2. In Render, create a **Blueprint** and connect the repository. `render.yaml` supplies the settings automatically.
3. If creating a Web Service manually, use:
   - Build command: `pip install -r requirements.txt`
   - Start command: `uvicorn app:app --host 0.0.0.0 --port $PORT`
4. After deployment, use the public `onrender.com` URL. The computer and local terminal do not need to remain on.

## Data status

The included processed file is based on a reproducible sample of 10,000 customers and 230,164 transactions. It is not H&M's complete operational population. Economic values in the decision calculator are assumptions and are visibly labelled.

## Rebuilding processed data

Place `articles.csv` or `articles.csv.zip`, `customers.csv` or `customers.csv.zip`, and `transactions_sample.csv` in `data/raw`, then run:

```powershell
.\.venv\Scripts\python.exe preprocess.py
```

## Test

```powershell
.\.venv\Scripts\python.exe -m pytest
```

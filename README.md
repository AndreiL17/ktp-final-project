# Running the GenAI Use Case Risk Advisor

To run the system locally, follow these steps:

## 1) Clone the repository
```bash
git clone git@github.com:AndreiL17/ktp-final-project.git
cd ktp-final-project
```

## 2) Create and activate a virtual environment
```bash
python3 -m venv .venv
source .venv/bin/activate      # macOS / Linux
.venv\Scripts\activate         # Windows
```

## 3) Install the required dependencies
```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## 4) Run the application
```bash
streamlit run main.py
```
If the command does not automatically open a browser page, the frontend is accessible at `http://localhost:8501`

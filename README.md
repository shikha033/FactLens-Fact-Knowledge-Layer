# FactLens — Fact Knowledge Layer

A lightweight document intelligence system that extracts meaningful facts from PDFs, grounds every fact in source evidence, and compares facts across documents to identify corroboration, contradiction, and context-dependent differences.

## Features

- Upload one or multiple PDF documents
- Extract numerical and semantic facts using Gemini
- Link every fact to its source document, page, and evidence quote
- Assign confidence scores to extracted facts
- Compare facts across different documents
- Identify:
  - Corroborated facts
  - Genuine contradictions
  - Contradictions reconciled by context
  - Uncertain relationships
- Record extraction and reasoning failures
- View facts, evidence, relationships, explanations, and confidence through a web UI
- Accept new PDFs without document-specific hard-coded rules

  ## Tech Stack

- **Backend:** Python, Flask
- **PDF Processing:** pdfplumber
- **LLM:** Google Gemini API
- **Database:** SQLite
- **Frontend:** HTML, CSS, JavaScript
- **Configuration:** Python dotenv

## Architecture

```text
                    PDF Documents
                         |
                         v
                 +----------------+
                 |   Flask API    |
                 +----------------+
                         |
                         v
                 +----------------+
                 | PDF Processing |
                 +----------------+
                         |
                         v
                 +----------------+
                 | Gemini LLM     |
                 | Fact Extraction|
                 +----------------+
                         |
                         v
              Evidence-backed Facts
                         |
                         v
                 +----------------+
                 | SQLite Storage |
                 +----------------+
                         |
                         v
              Cross-document Matching
                         |
                         v
                 +----------------+
                 | Gemini Reasoning|
                 +----------------+
                         |
                         v
       Corroboration / Contradiction /
       Context / Uncertain Relationships
                         |
                         v
                 Web Dashboard
```

## Setup and Run

### 1. Clone the repository

```bash
git clone <YOUR_GITHUB_REPOSITORY_URL>
cd fact-knowledge-layer
```

### 2. Create a virtual environment

#### Windows PowerShell

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

#### macOS / Linux

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
python -m pip install -r requirements.txt
```

### 4. Configure API Key

Create a `.env` file in the project root. A `.env.example` file is provided for reference.

```env
GEMINI_API_KEY=YOUR_GEMINI_API_KEY
GEMINI_MODEL=gemini-3.6-flash
```

### 5. Run the application

#### Windows PowerShell

```powershell
python app.py
```

Open:

```text
http://127.0.0.1:5000
```

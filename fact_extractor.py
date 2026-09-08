import os
import json
from google import genai
from google.genai import types
from dotenv import load_dotenv


load_dotenv()


class FactExtractor:

    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")

        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY is not set in the .env file."
            )

        self.client = genai.Client(api_key=api_key)

        self.model_name = os.getenv(
            "GEMINI_MODEL",
            "gemini-3.7-flash"
        )

        self.failures = []

    def extract_facts(self, pdf_path):

        self.failures = []
        facts = []

        try:
            # Upload the complete PDF to Gemini.
            # This is ONE file upload, rather than one request per page.
            uploaded_file = self.client.files.upload(
                file=pdf_path
            )

            prompt = """
You are the fact extraction component of a Fact Knowledge Layer.

Analyze the entire PDF and extract meaningful, evidence-backed facts.

IMPORTANT RULES:

1. Extract only facts explicitly supported by the PDF.
2. Do not invent or estimate information.
3. Focus on useful numerical and semantic facts.
4. Prefer facts involving:
   - financial values
   - revenue
   - profit/loss
   - growth
   - percentages
   - employee counts
   - operational metrics
   - targets
   - dates
   - geographic information
   - important business statements
5. Every fact MUST have source evidence.
6. The source must be an exact quote from the PDF.
7. Include the PDF page number where the evidence appears.
8. Preserve context such as:
   - financial year
   - quarter
   - date
   - unit
   - geography
   - population/scope
   - definition
9. Extract approximately 15-30 of the most useful facts from the entire document.
10. Do not create duplicate facts.
11. If a fact is not clearly supported by the document, do not include it.

Return ONLY a JSON array.

Each object must have exactly these fields:

{
    "fact": "Clear factual statement",
    "type": "numerical | financial | operational | demographic | temporal | geographic | general",
    "source": "Exact supporting quote from the PDF",
    "page": 1,
    "confidence": 0.95
}

The page number must be the actual PDF page containing the source evidence.

Analyze the complete document, not just the first page.
"""

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[
                    prompt,
                    uploaded_file
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )

            response_text = response.text.strip()

            parsed = json.loads(response_text)

            if not isinstance(parsed, list):
                raise ValueError(
                    "Gemini returned something other than a JSON array."
                )

            for item in parsed:

                if not isinstance(item, dict):
                    continue

                fact = str(
                    item.get("fact", "")
                ).strip()

                source = str(
                    item.get("source", "")
                ).strip()

                fact_type = str(
                    item.get("type", "general")
                ).strip()

                page = item.get("page")

                try:
                    page = int(page)
                except (ValueError, TypeError):
                    page = None

                try:
                    confidence = float(
                        item.get("confidence", 0.8)
                    )
                except (ValueError, TypeError):
                    confidence = 0.8

                confidence = max(
                    0.0,
                    min(1.0, confidence)
                )

                if not fact or not source:
                    continue

                facts.append({
                    "fact": fact,
                    "type": fact_type,
                    "page": page,
                    "source": source,
                    "confidence": confidence
                })

            if not facts:
                self.failures.append({
                    "page": None,
                    "type": "no_valid_facts",
                    "message": (
                        "Gemini processed the PDF but returned "
                        "no valid evidence-backed facts."
                    )
                })

        except json.JSONDecodeError as e:

            self.failures.append({
                "page": None,
                "type": "json_error",
                "message": (
                    f"Gemini returned invalid JSON: {str(e)}"
                )
            })

        except Exception as e:

            self.failures.append({
                "page": None,
                "type": "llm_error",
                "message": str(e)
            })

        return facts
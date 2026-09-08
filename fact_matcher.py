import os
import json
import re
from google import genai
from google.genai import types
from dotenv import load_dotenv


load_dotenv()


class FactMatcher:

    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")

        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY is not set. Please add it to your .env file."
            )

        self.client = genai.Client(api_key=api_key)

        self.model_name = os.getenv(
            "GEMINI_MODEL",
            "gemini-3.7-flash"
        )

    def extract_numbers(self, text):
        """
        Extract numerical values from a fact.
        Used only as supporting information for matching.
        """
        numbers = re.findall(
            r"[-+]?\d+(?:,\d{3})*(?:\.\d+)?%?",
            text
        )

        return numbers

    def match_facts(self, fact1, fact2):
        """
        Compare two facts and determine their relationship.
        """

        prompt = f"""
You are comparing two factual claims extracted from different documents.

Your task is to determine whether the facts:

1. CORROBORATED
   - They describe the same underlying fact.
   - The wording may be different.
   - Small numerical differences caused by rounding are acceptable.

2. CONTRADICTED
   - They describe the same subject, metric and comparable context,
     but make genuinely incompatible claims.

3. RECONCILED_BY_CONTEXT
   - They appear contradictory at first,
     but the difference is explained by context.
   - Examples:
     * different years
     * different quarters
     * different geographic scope
     * different populations
     * different units
     * different definitions
     * point-in-time vs annual values

4. UNCERTAIN
   - There is not enough information to confidently determine
     the relationship.

5. UNRELATED
   - The two facts concern different subjects or metrics.

IMPORTANT:
- Do not assume two numbers are contradictory just because they differ.
- Always consider time, unit, scope and definition.
- Do not invent missing context.
- If context is insufficient, use UNCERTAIN.

FACT 1:
{fact1}

FACT 2:
{fact2}

Return ONLY valid JSON in this format:

{{
  "relationship": "CORROBORATED | CONTRADICTED | RECONCILED_BY_CONTEXT | UNCERTAIN | UNRELATED",
  "explanation": "Short explanation of why this relationship was selected.",
  "confidence": 0.0
}}
"""

        try:

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )

            result = json.loads(response.text)

            relationship = str(
                result.get("relationship", "UNCERTAIN")
            ).upper()

            allowed = {
                "CORROBORATED",
                "CONTRADICTED",
                "RECONCILED_BY_CONTEXT",
                "UNCERTAIN",
                "UNRELATED"
            }

            if relationship not in allowed:
                relationship = "UNCERTAIN"

            try:
                confidence = float(
                    result.get("confidence", 0.5)
                )
            except (ValueError, TypeError):
                confidence = 0.5

            confidence = max(0.0, min(1.0, confidence))

            explanation = str(
                result.get(
                    "explanation",
                    "No explanation provided."
                )
            ).strip()

            return {
                "relationship": relationship,
                "explanation": explanation,
                "confidence": confidence
            }

        except json.JSONDecodeError:
            return {
                "relationship": "UNCERTAIN",
                "explanation": "Gemini returned an invalid JSON response.",
                "confidence": 0.0
            }

        except Exception as e:
            return {
                "relationship": "UNCERTAIN",
                "explanation": f"Comparison failed: {str(e)}",
                "confidence": 0.0
            }
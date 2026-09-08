import os
import sqlite3
from datetime import datetime

from flask import Flask, request, jsonify, render_template
from werkzeug.utils import secure_filename

from fact_extractor import FactExtractor
from fact_matcher import FactMatcher


app = Flask(__name__)

UPLOAD_FOLDER = "uploads"
DATABASE = "facts.db"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024


extractor = FactExtractor()
matcher = FactMatcher()


# ---------------------------------------------------------
# DATABASE
# ---------------------------------------------------------

def get_db():
    #conn = sqlite3.connect(DATABASE)
    conn=sqlite3.connect(DATABASE, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            upload_time TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id INTEGER NOT NULL,
            fact TEXT NOT NULL,
            fact_type TEXT,
            page_number INTEGER,
            source_quote TEXT,
            confidence REAL,
            FOREIGN KEY (doc_id) REFERENCES documents(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS relationships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fact_id1 INTEGER NOT NULL,
            fact_id2 INTEGER NOT NULL,
            relationship_type TEXT NOT NULL,
            explanation TEXT,
            confidence REAL,
            FOREIGN KEY (fact_id1) REFERENCES facts(id),
            FOREIGN KEY (fact_id2) REFERENCES facts(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS failures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id INTEGER NOT NULL,
            page_number INTEGER,
            failure_type TEXT,
            message TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (doc_id) REFERENCES documents(id)
        )
    """)

    conn.commit()
    conn.close()


init_db()


# ---------------------------------------------------------
# HOME
# ---------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


# ---------------------------------------------------------
# UPLOAD PDF
# ---------------------------------------------------------

@app.route("/upload", methods=["POST"])
def upload():

    if "file" not in request.files:
        return jsonify({
            "success": False,
            "error": "No file uploaded."
        }), 400

    file = request.files["file"]

    if not file.filename:
        return jsonify({
            "success": False,
            "error": "No file selected."
        }), 400

    if not file.filename.lower().endswith(".pdf"):
        return jsonify({
            "success": False,
            "error": "Only PDF files are supported."
        }), 400

    filename = secure_filename(file.filename)

    if not filename:
        return jsonify({
            "success": False,
            "error": "Invalid filename."
        }), 400

    filepath = os.path.join(
        app.config["UPLOAD_FOLDER"],
        filename
    )

    file.save(filepath)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO documents (filename, upload_time)
        VALUES (?, ?)
        """,
        (
            filename,
            datetime.now().isoformat()
        )
    )

    doc_id = cursor.lastrowid

    conn.commit()
    conn.close()

    # Extract facts
    facts = extractor.extract_facts(filepath)

    conn = get_db()
    cursor = conn.cursor()

    for fact in facts:

        cursor.execute(
            """
            INSERT INTO facts
            (
                doc_id,
                fact,
                fact_type,
                page_number,
                source_quote,
                confidence
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                doc_id,
                fact["fact"],
                fact.get("type", "general"),
                fact.get("page"),
                fact.get("source"),
                fact.get("confidence", 0.8)
            )
        )

    # Store extraction failures separately
    for failure in extractor.failures:

        cursor.execute(
            """
            INSERT INTO failures
            (
                doc_id,
                page_number,
                failure_type,
                message,
                created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                doc_id,
                failure.get("page"),
                failure.get("type"),
                failure.get("message"),
                datetime.now().isoformat()
            )
        )

    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "filename": filename,
        "facts_extracted": len(facts),
        "failures": len(extractor.failures)
    })


# ---------------------------------------------------------
# GET FACTS
# ---------------------------------------------------------

@app.route("/facts", methods=["GET"])
def get_facts():

    conn = get_db()

    rows = conn.execute("""
        SELECT
            facts.id,
            facts.fact,
            facts.fact_type,
            facts.page_number,
            facts.source_quote,
            facts.confidence,
            documents.filename
        FROM facts
        JOIN documents
        ON facts.doc_id = documents.id
        ORDER BY facts.id
    """).fetchall()

    conn.close()

    facts = []

    for row in rows:

        facts.append({
            "id": row["id"],
            "fact": row["fact"],
            "type": row["fact_type"],
            "page": row["page_number"],
            "source": row["source_quote"],
            "confidence": row["confidence"],
            "document": row["filename"]
        })

    return jsonify(facts)


# ---------------------------------------------------------
# ANALYZE RELATIONSHIPS
# ---------------------------------------------------------

@app.route("/analyze", methods=["POST"])
def analyze():

    conn = get_db()

    # Remove previous relationships so repeated
    # Analyze clicks do not create duplicates.
    conn.execute("DELETE FROM relationships")
    conn.commit()

    rows = conn.execute("""
        SELECT
            facts.id,
            facts.doc_id,
            facts.fact,
            facts.fact_type,
            facts.page_number,
            facts.source_quote,
            facts.confidence,
            documents.filename
        FROM facts
        JOIN documents
        ON facts.doc_id = documents.id
        ORDER BY facts.id
    """).fetchall()

    relationships_found = 0

    # Compare facts belonging to different documents.
    for i in range(len(rows)):

        for j in range(i + 1, len(rows)):

            fact1 = rows[i]
            fact2 = rows[j]

            if fact1["doc_id"] == fact2["doc_id"]:
                continue

            # Give Gemini the actual facts and their evidence.
            fact_text_1 = f"""
Fact:
{fact1["fact"]}

Document:
{fact1["filename"]}

Page:
{fact1["page_number"]}

Source evidence:
{fact1["source_quote"]}
"""

            fact_text_2 = f"""
Fact:
{fact2["fact"]}

Document:
{fact2["filename"]}

Page:
{fact2["page_number"]}

Source evidence:
{fact2["source_quote"]}
"""

            result = matcher.match_facts(
                fact_text_1,
                fact_text_2
            )

            relationship = result["relationship"]

            # We do not need to store unrelated facts.
            if relationship == "UNRELATED":
                continue

            conn.execute(
                """
                INSERT INTO relationships
                (
                    fact_id1,
                    fact_id2,
                    relationship_type,
                    explanation,
                    confidence
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    fact1["id"],
                    fact2["id"],
                    relationship,
                    result["explanation"],
                    result["confidence"]
                )
            )

            relationships_found += 1

    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "relationships_found": relationships_found
    })


# ---------------------------------------------------------
# GET RELATIONSHIPS
# ---------------------------------------------------------

@app.route("/relationships", methods=["GET"])
def get_relationships():

    conn = get_db()

    rows = conn.execute("""
        SELECT
            r.id,
            r.relationship_type,
            r.explanation,
            r.confidence,

            f1.fact AS fact1,
            f1.page_number AS page1,
            f1.source_quote AS source1,

            f2.fact AS fact2,
            f2.page_number AS page2,
            f2.source_quote AS source2,

            d1.filename AS document1,
            d2.filename AS document2

        FROM relationships r

        JOIN facts f1
        ON r.fact_id1 = f1.id

        JOIN facts f2
        ON r.fact_id2 = f2.id

        JOIN documents d1
        ON f1.doc_id = d1.id

        JOIN documents d2
        ON f2.doc_id = d2.id

        ORDER BY r.id
    """).fetchall()

    conn.close()

    relationships = []

    for row in rows:

        relationships.append({
            "id": row["id"],
            "relationship": row["relationship_type"],
            "explanation": row["explanation"],
            "confidence": row["confidence"],

            "fact1": row["fact1"],
            "document1": row["document1"],
            "page1": row["page1"],
            "source1": row["source1"],

            "fact2": row["fact2"],
            "document2": row["document2"],
            "page2": row["page2"],
            "source2": row["source2"]
        })

    return jsonify(relationships)


# ---------------------------------------------------------
# FOUR REQUIRED CASES
# ---------------------------------------------------------

@app.route("/four-cases", methods=["GET"])
def four_cases():

    conn = get_db()

    relationship_rows = conn.execute("""
        SELECT
            r.relationship_type,
            r.explanation,
            r.confidence,

            f1.fact AS fact1,
            f1.page_number AS page1,
            f1.source_quote AS source1,
            d1.filename AS document1,

            f2.fact AS fact2,
            f2.page_number AS page2,
            f2.source_quote AS source2,
            d2.filename AS document2

        FROM relationships r

        JOIN facts f1
        ON r.fact_id1 = f1.id

        JOIN facts f2
        ON r.fact_id2 = f2.id

        JOIN documents d1
        ON f1.doc_id = d1.id

        JOIN documents d2
        ON f2.doc_id = d2.id

        WHERE r.relationship_type IN
        (
            'CORROBORATED',
            'CONTRADICTED',
            'RECONCILED_BY_CONTEXT'
        )

        ORDER BY r.id
    """).fetchall()

    failures = conn.execute("""
        SELECT
            failures.page_number,
            failures.failure_type,
            failures.message,
            documents.filename
        FROM failures
        JOIN documents
        ON failures.doc_id = documents.id
        ORDER BY failures.id
    """).fetchall()

    conn.close()

    cases = {
        "corroboration": [],
        "contradiction": [],
        "context": [],
        "extraction_failure": []
    }

    for row in relationship_rows:

        case = {
            "fact1": row["fact1"],
            "document1": row["document1"],
            "page1": row["page1"],
            "source1": row["source1"],

            "fact2": row["fact2"],
            "document2": row["document2"],
            "page2": row["page2"],
            "source2": row["source2"],

            "explanation": row["explanation"],
            "confidence": row["confidence"]
        }

        if row["relationship_type"] == "CORROBORATED":
            cases["corroboration"].append(case)

        elif row["relationship_type"] == "CONTRADICTED":
            cases["contradiction"].append(case)

        elif row["relationship_type"] == "RECONCILED_BY_CONTEXT":
            cases["context"].append(case)

    for row in failures:

        cases["extraction_failure"].append({
            "document": row["filename"],
            "page": row["page_number"],
            "type": row["failure_type"],
            "message": row["message"]
        })

    return jsonify({
        "counts": {
            "corroboration": len(cases["corroboration"]),
            "contradiction": len(cases["contradiction"]),
            "context": len(cases["context"]),
            "extraction_failure": len(cases["extraction_failure"])
        },
        "cases": cases
    })


# ---------------------------------------------------------
# CLEAR DATABASE
# ---------------------------------------------------------

@app.route("/clear", methods=["POST"])
def clear_database():

    conn = get_db()

    conn.execute("DELETE FROM relationships")
    conn.execute("DELETE FROM facts")
    conn.execute("DELETE FROM failures")
    conn.execute("DELETE FROM documents")

    conn.commit()
    conn.close()

    # Remove uploaded PDFs
    for filename in os.listdir(UPLOAD_FOLDER):

        filepath = os.path.join(
            UPLOAD_FOLDER,
            filename
        )

        if os.path.isfile(filepath):
            try:
                os.remove(filepath)
            except OSError:
                pass

    return jsonify({
        "success": True,
        "message": "Database and uploaded files cleared."
    })


# ---------------------------------------------------------
# RUN
# ---------------------------------------------------------

if __name__ == "__main__":
    app.run(
        debug=True,
        port=5000
    )
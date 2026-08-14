from backend.database import SessionLocal
from backend.models import KnowledgeDocument
from backend.rag import create_embedding


documents = [
    """
    Password Reset:
    Users can reset their password from the account settings page.
    If they cannot access their account, they should contact support.
    """,

    """
    Account Login:
    If login fails, verify the email address and password.
    If the problem continues, reset the password or contact support.
    """,

    """
    Refunds:
    Refund requests should be submitted through the support system.
    Refund eligibility depends on the applicable refund policy.
    """,

    """
    Technical Problems:
    For technical problems, first restart the application and check
    the internet connection. If the problem continues, provide the
    error message to support.
    """,

    """
    Contact Support:
    If an issue cannot be resolved through the available troubleshooting
    steps, the user should contact the support team.
    """
]


db = SessionLocal()

try:
    for content in documents:

        embedding = create_embedding(content)

        document = KnowledgeDocument(
            content=content,
            embedding=embedding
        )

        db.add(document)

    db.commit()

    print("Knowledge base successfully populated!")

finally:
    db.close()
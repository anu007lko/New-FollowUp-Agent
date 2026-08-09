"""
Encrypted persistence layer interface (M1 stub).
SQLCipher / SQLite storage boundary.
"""

class PersistenceAdapterStub:
    """Stub for SQLCipher / SQLite encrypted local database."""
    
    def is_database_initialized(self) -> bool:
        """Check if local database exists."""
        return False

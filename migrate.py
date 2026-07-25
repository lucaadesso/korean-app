from app.database import engine, Base
import app.models
Base.metadata.create_all(bind=engine)
print("Migration completed")
